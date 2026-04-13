# EC2 bare-metal bootstrap (Phase A)

One-time sequence that brings a fresh t4g.small from `terraform apply` to a
working `brain-core` + `brain-web` bare-metal stack reachable over SSM
port-forward. Docker containerization lands Day 2; this is the fast path that
ships tonight's minimum-viable loop.

## Prereqs

- `terraform apply` in `infra/terraform/` has completed. Instance is running,
  SSM agent is online, `brain/github_pat` is in Secrets Manager.
- Local AWS CLI has a profile with `AdministratorAccess` (e.g. `brain-terraform`
  user). Export `AWS_PROFILE=brain`.
- `session-manager-plugin` installed locally (for port-forward). On Mac without
  `sudo`: download the zip directly from
  `https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac_arm64/sessionmanager-bundle.zip`,
  extract, and drop the binary into `~/.local/bin/`.

## 1. Seed Claude credentials into Secrets Manager

On the Mac where Claude Code is already authed, read the OAuth credential
from Keychain and seed it:

```bash
CREDS=$(security find-generic-password -a "$USER" -s "Claude Code-credentials" -w)
aws secretsmanager create-secret \
  --name brain/claude_credentials \
  --secret-string "$CREDS" \
  --region us-west-2
```

This is a claude.ai subscription OAuth credential (access + refresh tokens).
Refresh is automatic via Claude Code; the stored blob only needs to be rotated
if the session is revoked.

## 2. Clone vault + install tooling on EC2

Via `aws ssm send-command` (see `infra/ec2/commands/bootstrap.sh`):

- Pull `brain/github_pat`, clone `YogeshSeeni/second-brain` into `/var/brain`
- Install Node 22 (nodesource apt repo)
- Install `uv` into `/home/ubuntu/.local/bin`
- Install `@anthropic-ai/claude-code` globally

## 3. Install brain-core + brain-web dependencies

Via SSM:

```bash
sudo -u ubuntu bash -lc "cd /var/brain/apps/brain-core && uv sync"
sudo -u ubuntu bash -lc "cd /var/brain/apps/brain-web && npm install --no-audit --no-fund"
sudo -u ubuntu bash -lc "cd /var/brain/apps/brain-web && npx next build"
```

## 4. Deploy claude credentials file

Via SSM, fetch `brain/claude_credentials` and drop it at
`/home/ubuntu/.claude/.credentials.json` with `chmod 600`. Verify with
`claude auth status`.

## 5. Install + start systemd units

Copy `infra/ec2/systemd/brain-core.service` and
`infra/ec2/systemd/brain-web.service` to `/etc/systemd/system/`, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now brain-core.service
sudo systemctl enable --now brain-web.service
```

Smoke test from inside the box:

```bash
curl -sS http://localhost:8000/api/health
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:3000/chat
```

Expect `{"ok":true}` and `200`.

## 6. Port-forward from the Mac

```bash
aws ssm start-session \
  --target <instance-id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters portNumber=3000,localPortNumber=3000 \
  --region us-west-2
```

Open `http://localhost:3000/chat` in Safari.

## Known gaps (Phase A scope)

- No TLS, no public URL, no auth — this entire stack is localhost-only over
  SSM. Public HTTPS + NextAuth lands Day 2 (see `wiki/` plan).
- Credentials live as a plain JSON file at `~/.claude/.credentials.json`. Acceptable
  because the EC2 box is SSM-only and single-tenant.
- No cron tick, no watcher, no topic threads — all Day 3+.
