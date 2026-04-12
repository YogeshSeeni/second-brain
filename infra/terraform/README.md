# Terraform: brain-runner

Spins up the EC2 host that runs the Claude Code assistant on a cron. Single
instance, single region, no load balancer, no autoscaling. Deliberately
boring.

## Prereqs (run once on your Mac)

```zsh
# AWS SSO configured with a profile named `brain`
aws sts get-caller-identity --profile brain

# Tailscale account + an ACL that authorizes tag:brain for autogroup:admin
# Generate a reusable pre-auth key at:
#   https://login.tailscale.com/admin/settings/keys
# Copy the key value — you'll paste it into the command below.

# Seed the Tailscale pre-auth key into Secrets Manager BEFORE terraform apply.
# The user data script fetches it on first boot.
# Replace <<TAILSCALE_KEY>> with the value you just generated.
aws secretsmanager create-secret \
    --profile brain \
    --name brain/tailscale_authkey \
    --description "Tailscale pre-auth key for brain-runner" \
    --secret-string '<<TAILSCALE_KEY>>'

# (Optional, seeded later for the GitHub clone step)
# Replace <<GITHUB_PAT>> with a fresh PAT scoped to repo on YogeshSeeni/second-brain.
aws secretsmanager create-secret \
    --profile brain \
    --name brain/github_pat \
    --description "GitHub PAT with repo scope on YogeshSeeni/second-brain" \
    --secret-string '<<GITHUB_PAT>>'
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
# SSM session (no SSH keys, no ports)
aws ssm start-session --target <instance-id> --profile brain --region us-west-2

# Once inside, switch to ubuntu user and verify tailscale
sudo -iu ubuntu
tailscale status
docker --version
aws sts get-caller-identity
```

From your Mac (once on the same tailnet):

```zsh
ssh brain-runner              # via Tailscale SSH (no keys)
```

## What user data does (first boot)

1. Installs Docker, AWS CLI v2, git, python, cron, Tailscale.
2. Fetches `brain/tailscale_authkey` from Secrets Manager and joins the
   tailnet with hostname `brain-runner`, tag `tag:brain`, Tailscale SSH on.
3. Creates `/var/brain` owned by the `ubuntu` user (the vault clone target —
   actual clone happens later in the SSM session, because the GitHub PAT
   lookup wants to run after we've verified the secret exists).

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
aws secretsmanager delete-secret --profile brain --secret-id brain/tailscale_authkey --force-delete-without-recovery
aws secretsmanager delete-secret --profile brain --secret-id brain/github_pat --force-delete-without-recovery
```

## Notes

- `ignore_changes = [user_data, ami]` on the instance — so re-applying doesn't
  force a replace when you tweak user data or when Canonical publishes a new
  AMI. To actually bake in a user data change, taint the instance explicitly:
  `terraform taint aws_instance.brain && terraform apply`.
- The security group is egress-only. Ingress is exclusively via Tailscale
  (userspace networking) and AWS SSM (agent polls SSM endpoints outbound).
  There is no open port 22.
- The default VPC is fine for this workload. A dedicated VPC + private
  subnets + NAT gateway is overkill for a single instance and adds ~$30/mo.
