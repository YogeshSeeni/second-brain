output "instance_id" {
  description = "EC2 instance ID. Use for SSM: aws ssm start-session --target <id> --profile brain"
  value       = aws_instance.brain.id
}

output "instance_private_ip" {
  description = "Private IP inside the default VPC"
  value       = aws_instance.brain.private_ip
}

output "ssm_command" {
  description = "Ready-to-run SSM session command"
  value       = "aws ssm start-session --target ${aws_instance.brain.id} --profile ${var.profile} --region ${var.region}"
}
