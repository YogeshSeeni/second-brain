terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.profile
  default_tags {
    tags = var.tags
  }
}

data "aws_caller_identity" "current" {}

# Ubuntu 24.04 LTS arm64, Canonical official
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Default VPC + a subnet in the first AZ — keeps tonight's rollout simple;
# revisit with a dedicated VPC later if Tailscale-only access is ever
# compromised.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "brain" {
  name        = "brain-runner"
  description = "Egress-only; ingress is via Tailscale + SSM, no open ports."
  vpc_id      = data.aws_vpc.default.id

  egress {
    description      = "all egress — tailscale, github, claude api, secrets manager, ntfy"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

# IAM role + instance profile — SSM + Secrets Manager read on brain/*
resource "aws_iam_role" "brain" {
  name = "brain-runner"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.brain.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "secrets" {
  name = "brain-secrets-read"
  role = aws_iam_role.brain.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      Resource = "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:brain/*"
    }]
  })
}

resource "aws_iam_instance_profile" "brain" {
  name = "brain-runner"
  role = aws_iam_role.brain.name
}

# User data: install docker, aws cli, tailscale, join tailnet, clone vault.
# Claude Code install + OAuth happens later via SSM session (not here — OAuth
# requires a browser round-trip).
locals {
  user_data = <<-EOT
    #!/bin/bash
    set -eux
    export DEBIAN_FRONTEND=noninteractive

    # Timezone
    timedatectl set-timezone '${var.timezone}'

    # Base packages
    apt-get update -y
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release \
        git jq unzip tini \
        python3 python3-pip python3-venv \
        cron

    # Docker
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    usermod -aG docker ubuntu
    systemctl enable --now docker

    # AWS CLI v2
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscliv2.zip
    unzip -q /tmp/awscliv2.zip -d /tmp
    /tmp/aws/install
    rm -rf /tmp/aws /tmp/awscliv2.zip

    # Tailscale
    curl -fsSL https://tailscale.com/install.sh | sh

    # Join tailnet using pre-auth key from Secrets Manager (retry a few times;
    # IAM role propagation can lag).
    for i in 1 2 3 4 5; do
        if TS_KEY="$(aws secretsmanager get-secret-value --region ${var.region} --secret-id '${var.tailscale_authkey_secret_name}' --query SecretString --output text 2>/dev/null)"; then
            tailscale up --authkey="$TS_KEY" --ssh --hostname=brain-runner --accept-routes --advertise-tags=tag:brain
            break
        fi
        sleep 5
    done

    # SSM agent is pre-installed on the Canonical Ubuntu AMI — just make sure
    # it's running
    snap install amazon-ssm-agent --classic || true
    systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent || true

    # Vault bootstrap — clone into /var/brain. The repo is private; we need
    # auth. For tonight, we defer the clone to the interactive SSM session
    # step where the user pastes a GitHub PAT (stored later in Secrets
    # Manager under brain/github_pat for subsequent reboots).
    install -d -o ubuntu -g ubuntu /var/brain
    echo "user data done at $(date)" > /var/log/brain-userdata.log
  EOT
}

resource "aws_instance" "brain" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = tolist(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.brain.id]
  iam_instance_profile   = aws_iam_instance_profile.brain.name
  user_data              = local.user_data

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_size           = var.root_volume_gb
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Name = "brain-runner"
  }

  lifecycle {
    # Changing user_data would force a replace — block that by default so we
    # don't nuke the instance on every terraform apply. Update in place via
    # SSM session instead.
    ignore_changes = [user_data, ami]
  }
}
