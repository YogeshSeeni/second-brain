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

output "public_ip" {
  description = "Elastic IP for the brain instance. Point DuckDNS A record at this."
  value       = aws_eip.brain.public_ip
}

output "brain_worker_ecr_url" {
  description = "ECR repo URL for pushing brain-worker:vN"
  value       = aws_ecr_repository.brain_worker.repository_url
}
