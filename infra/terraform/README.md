# Terraform: brain-runner

Spins up the EC2 host that runs the Claude Code assistant on a cron. Single
instance, single region, no load balancer, no autoscaling. Deliberately
boring. Access via AWS SSM Session Manager only — no SSH, no open ports.

## Prereqs (run once on your Mac)

```zsh
# AWS SSO configured with a profile named `brain`
aws sts get-caller-identity --profile brain

# Seed the GitHub PAT into Secrets Manager. The docker entrypoint on the
# instance uses it to clone the private vault repo.
# Replace <<GITHUB_PAT>> with a fresh PAT scoped to repo on YogeshSeeni/second-brain.
aws secretsmanager create-secret \
    --profile brain \
    --region us-west-2 \
    --name brain/github_pat \
    --description "GitHub PAT with repo scope on YogeshSeeni/second-brain" \
    --secret-string '<<GITHUB_PAT>>'

# ntfy topic (push notifications)
aws secretsmanager create-secret \
    --profile brain \
    --region us-west-2 \
    --name brain/ntfy_topic \
    --secret-string 'brain-yogesh'
```

## Apply

```zsh
cd infra/terraform
terraform init
terraform plan -out=tf.plan
terraform apply tf.plan
```

Expect ~3 min. Outputs include the instance ID and a ready-to-run SSM
command.

## Connect

```zsh
# SSM session (no SSH keys, no ports, works from any network with IAM creds)
aws ssm start-session --target <instance-id> --profile brain --region us-west-2

# Once inside, switch to ubuntu user and verify
sudo -iu ubuntu
docker --version
aws sts get-caller-identity
```

## What user data does (first boot)

1. Installs Docker, AWS CLI v2, git, python, cron.
2. Enables the AWS SSM agent so `aws ssm start-session` works.
3. Creates `/var/brain` owned by the `ubuntu` user. The docker entrypoint
   clones the vault into that directory on first container start.

Everything Claude-specific (Docker image build, compose up, `claude login`)
happens in a follow-up SSM session — user data intentionally does not run
anything that requires network round-trips back to a browser.

## Destroy

```zsh
terraform destroy
```

Secrets are NOT destroyed with the instance — delete them explicitly if you
want a full tear-down:

```zsh
aws secretsmanager delete-secret --profile brain --region us-west-2 \
    --secret-id brain/github_pat --force-delete-without-recovery
aws secretsmanager delete-secret --profile brain --region us-west-2 \
    --secret-id brain/ntfy_topic --force-delete-without-recovery
aws secretsmanager delete-secret --profile brain --region us-west-2 \
    --secret-id brain/claude_credentials --force-delete-without-recovery
```

## Notes

- `ignore_changes = [user_data, ami]` on the instance — so re-applying doesn't
  force a replace when you tweak user data or when Canonical publishes a new
  AMI. To actually bake in a user data change, taint the instance explicitly:
  `terraform taint aws_instance.brain && terraform apply`.
- The security group is egress-only. Ingress is exclusively via AWS SSM
  (agent polls SSM endpoints outbound — no inbound rule needed). There is no
  open port 22.
- The default VPC is fine for this workload. A dedicated VPC + private
  subnets + NAT gateway is overkill for a single instance and adds ~$30/mo.
- Tailscale was considered and dropped for tonight's rollout — SSM covers
  every access pattern we need. Add back post-rollout if ergonomics demand.
