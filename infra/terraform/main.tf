terraform {
  required_version = ">= 1.5.0"
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

# Default VPC + a subnet in the first AZ — simple by design. Access is via
# AWS SSM Session Manager only (IAM-authenticated, no open ports).
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
  name_prefix = "brain-runner-"
  description = "Egress-all; ingress :80/:443 for Caddy + Lets Encrypt; SSM handles ops."
  vpc_id      = data.aws_vpc.default.id

  lifecycle {
    create_before_destroy = true
  }

  ingress {
    description      = "HTTP: Lets Encrypt HTTP-01 challenge and redirect to 443"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "HTTPS: Caddy serves the web UI"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description      = "all egress: github, claude api, secrets manager, ntfy, ssm"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

# Elastic IP — keeps the public address stable across instance stop/start so
# the DuckDNS record doesn't need to chase the assignment.
resource "aws_eip" "brain" {
  domain = "vpc"
  tags = {
    Name = "brain-runner"
  }
}

resource "aws_eip_association" "brain" {
  instance_id   = aws_instance.brain.id
  allocation_id = aws_eip.brain.id
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
  name = "brain-secrets-rw"
  role = aws_iam_role.brain.id

  # PutSecretValue is scoped to brain/claude_credentials only — the runner
  # writes refreshed Claude Code OAuth tokens back to this one secret so a
  # reboot never resurrects a stale refresh token. Other brain/* secrets
  # (github_pat, whoop, etc.) remain read-only.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadAllBrainSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:brain/*"
      },
      {
        Sid    = "WriteClaudeCredentialsOnly"
        Effect = "Allow"
        Action = [
          "secretsmanager:PutSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:brain/claude_credentials-*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "brain" {
  name = "brain-runner"
  role = aws_iam_role.brain.name
}

# User data: install docker, aws cli, prep vault dir. Access is via AWS SSM
# Session Manager — no Tailscale, no SSH. Claude Code install + OAuth happens
# later inside the docker container via SSM session (not here — OAuth needs a
# browser round-trip).
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

    # SSM agent — pre-installed on the Canonical Ubuntu AMI, just make sure
    # it's enabled (required for `aws ssm start-session` access)
    snap install amazon-ssm-agent --classic || true
    systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent || true

    # Vault bootstrap — clone into /var/brain. The repo is private; entrypoint
    # inside the docker container pulls brain/github_pat from Secrets Manager
    # and clones there. We just create the mount point.
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
