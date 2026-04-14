resource "aws_iam_role" "brain_instance_v1" {
  name = "brain-instance-v1"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "brain_ssm_v1" {
  role       = aws_iam_role.brain_instance_v1.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "brain_runtime_v1" {
  name = "brain-runtime-v1"
  role = aws_iam_role.brain_instance_v1.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsRead"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
        Resource = [
          "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:brain/*",
        ]
      },
      {
        Sid    = "SecretsWriteClaude"
        Effect = "Allow"
        Action = ["secretsmanager:PutSecretValue"]
        Resource = [
          "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:brain/claude_credentials-*",
        ]
      },
      {
        Sid    = "EcrPull"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
        ]
        Resource = "*"
      },
      {
        Sid      = "AttachBrainVolume"
        Effect   = "Allow"
        Action   = ["ec2:AttachVolume", "ec2:DetachVolume", "ec2:DescribeVolumes"]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_instance_profile" "brain_v1" {
  name = "brain-instance-v1"
  role = aws_iam_role.brain_instance_v1.name
}

resource "aws_launch_template" "brain_v1" {
  name_prefix   = "brain-v1-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = "t4g.large"

  iam_instance_profile {
    arn = aws_iam_instance_profile.brain_v1.arn
  }

  vpc_security_group_ids = [aws_security_group.brain.id]

  user_data = base64encode(file("${path.module}/../ec2/cloud-init-v2.yaml"))

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "enabled"
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "brain-v1"
      Role = "brain-runner"
      Env  = "prod"
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_autoscaling_group" "brain_v1" {
  name                      = "brain-v1"
  vpc_zone_identifier       = [data.aws_subnet.first_default.id]
  desired_capacity          = 1
  min_size                  = 1
  max_size                  = 1
  health_check_type         = "EC2"
  health_check_grace_period = 120

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "capacity-optimized"
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.brain_v1.id
        version            = "$Latest"
      }
      # Diversify instance types so a single-AZ capacity shortfall on one
      # size doesn't wedge the ASG. All ARM Graviton, all broadly comparable
      # to t4g.large — capacity-optimized strategy picks the cheapest
      # available at launch time. The persistent EBS is AZ-locked to
      # us-west-2a, so multi-AZ is not an option without a snapshot+migrate.
      override { instance_type = "t4g.large" }
      override { instance_type = "t4g.xlarge" }
      override { instance_type = "m6g.large" }
      override { instance_type = "m6g.xlarge" }
      override { instance_type = "c6g.large" }
      override { instance_type = "c6g.xlarge" }
      override { instance_type = "m7g.large" }
      override { instance_type = "c7g.large" }
    }
  }

  tag {
    key                 = "Name"
    value               = "brain-v1"
    propagate_at_launch = true
  }
}
