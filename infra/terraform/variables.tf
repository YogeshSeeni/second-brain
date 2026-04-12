variable "region" {
  description = "AWS region for the brain instance"
  type        = string
  default     = "us-west-2"
}

variable "profile" {
  description = "Local AWS CLI profile used by terraform"
  type        = string
  default     = "brain"
}

variable "instance_type" {
  description = "EC2 instance type. t4g.small is arm64, 2 vCPU, 2 GiB RAM — enough for Claude Code + Docker Compose."
  type        = string
  default     = "t4g.small"
}

variable "root_volume_gb" {
  description = "Root EBS volume size. 20 GiB fits Ubuntu + Docker + Playwright image + vault clone + logs."
  type        = number
  default     = 20
}

variable "vault_repo_url" {
  description = "Private GitHub repo that EC2 clones into /var/brain"
  type        = string
  default     = "https://github.com/YogeshSeeni/second-brain.git"
}

variable "tailscale_authkey_secret_name" {
  description = "Secrets Manager entry holding the Tailscale pre-auth key (plain string, not JSON)"
  type        = string
  default     = "brain/tailscale_authkey"
}

variable "timezone" {
  description = "Host timezone, used for cron schedules"
  type        = string
  default     = "America/Los_Angeles"
}

variable "tags" {
  description = "Common tags applied to every resource"
  type        = map(string)
  default = {
    Project     = "brain"
    ManagedBy   = "terraform"
    Environment = "prod"
  }
}
