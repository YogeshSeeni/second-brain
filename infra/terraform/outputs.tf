output "brain_worker_ecr_url" {
  description = "ECR repo URL for pushing brain-worker:vN"
  value       = aws_ecr_repository.brain_worker.repository_url
}

output "brain_state_volume_id" {
  description = "EBS volume id for /var/brain (persistent across Spot interruptions)"
  value       = aws_ebs_volume.brain_state.id
}

output "brain_asg_name" {
  value = aws_autoscaling_group.brain_v1.name
}

output "brain_launch_template_id" {
  value = aws_launch_template.brain_v1.id
}
