data "aws_subnet" "first_default" {
  id = element(data.aws_subnets.default.ids, 0)
}

resource "aws_ebs_volume" "brain_state" {
  availability_zone = data.aws_subnet.first_default.availability_zone
  size              = 200
  type              = "gp3"
  iops              = 3000
  throughput        = 125
  encrypted         = true

  tags = {
    Name = "brain-state"
    Role = "persistent-state-v1"
  }

  lifecycle {
    prevent_destroy = true
  }
}
