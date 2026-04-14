resource "aws_ecr_repository" "brain_worker" {
  name                 = "brain/brain-worker"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "brain_worker_retain_10" {
  repository = aws_ecr_repository.brain_worker.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
