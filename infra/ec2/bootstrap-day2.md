# Phase B / Day 2 — Auth + public HTTPS

Brings the already-running v0.2-skeleton (brain-core + brain-web on systemd,
SSM-only) to a public HTTPS URL gated by Google OAuth. Adds:

- Elastic IP + `:80`/`:443` ingress on the SG
- DuckDNS subdomain pointing at the EIP
- Caddy as reverse-proxy + TLS terminator
- NextAuth v5 (Google provider) with a single-email allowlist
- brain-core reachable only via Caddy's same-origin `/api/*` proxy

All existing Phase A runbook steps still apply. Don't re-run them. This file
is a layer on top.

## Prereqs

- Phase A complete. `i-083850f5231bf5048` is online, systemd units running.
- Local `AWS_PROFILE=brain`, `session-manager-plugin` installed.

## 1. Claim a DuckDNS subdomain

1. Go to `https://www.duckdns.org`, sign in with GitHub.
2. Register a subdomain, e.g. `brain-yogesh.duckdns.org`. Leave the IP blank
   for now — the updater script will fill it on first run.
3. Copy the DuckDNS token from the top of the page.

## 2. Create the Google OAuth client

1. Open `https://console.cloud.google.com/apis/credentials`, switch to (or
   create) a project for this brain app.
2. **OAuth consent screen** → External, add yourself as a test user.
3. **Credentials → Create credentials → OAuth client ID → Web application.**
   - Name: `brain-web`
   - Authorized redirect URIs:
     - `https://brain-yogesh.duckdns.org/api/auth/callback/google`
     - (Optional, local dev) `http://localhost:3000/api/auth/callback/google`
4. Save the **client ID** and **client secret**.

## 3. Apply the Terraform delta

```bash
cd infra/terraform
terraform plan    # should show: aws_eip.brain + aws_eip_association.brain + SG ingress rules
terraform apply
```

Record the `public_ip` output. Paste it into the DuckDNS record (one-time;
the updater timer keeps the subdomain alive but won't change the address once
it's set).

## 4. Seed secrets

```bash
# Generate a NextAuth session secret
AUTH_SECRET=$(openssl rand -base64 32)

# Bundle everything into a single Secrets Manager blob for atomic deploys.
aws secretsmanager create-secret \
  --name brain/web_env \
  --region us-west-2 \
  --secret-string "$(cat <<EOF
AUTH_SECRET=$AUTH_SECRET
AUTH_GOOGLE_ID=<paste client id>
AUTH_GOOGLE_SECRET=<paste client secret>
AUTH_TRUST_HOST=true
AUTH_URL=https://brain-yogesh.duckdns.org
ALLOWED_EMAILS=yogesh60@stanford.edu
NEXT_PUBLIC_BRAIN_CORE_URL=
EOF
)"

# DuckDNS token lives separately so it can rotate independently
aws secretsmanager create-secret \
  --name brain/duckdns \
  --region us-west-2 \
  --secret-string '{"domain":"brain-yogesh","token":"<paste duckdns token>"}'
```

The IAM policy in `main.tf` already grants `brain/*` read to the instance
role, so no policy changes needed.

## 5. Install Caddy + DuckDNS + Next build on EC2

All via `aws ssm send-command` (or an interactive `start-session`). The
commands assume you're shelled in as `ubuntu`:

```bash
# --- Caddy ---
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update -y && sudo apt-get install -y caddy

# --- DuckDNS updater ---
sudo install -m 0755 /var/brain/infra/ec2/duckdns/update.sh /usr/local/bin/duckdns-update.sh
sudo install -m 0644 /var/brain/infra/ec2/duckdns/brain-duckdns.service /etc/systemd/system/
sudo install -m 0644 /var/brain/infra/ec2/duckdns/brain-duckdns.timer /etc/systemd/system/

sudo mkdir -p /etc/default
DUCKDNS_JSON=$(aws secretsmanager get-secret-value --secret-id brain/duckdns --region us-west-2 --query SecretString --output text)
DOMAIN=$(echo "$DUCKDNS_JSON" | jq -r .domain)
TOKEN=$(echo "$DUCKDNS_JSON" | jq -r .token)
sudo tee /etc/default/brain-duckdns > /dev/null <<EOF
DUCKDNS_DOMAIN=$DOMAIN
DUCKDNS_TOKEN=$TOKEN
EOF
sudo chmod 0640 /etc/default/brain-duckdns

sudo systemctl daemon-reload
sudo systemctl enable --now brain-duckdns.timer
sudo systemctl start brain-duckdns.service   # fire once immediately
sudo cat /var/log/brain-duckdns.log          # expect "OK"

# --- Caddy config ---
sudo install -m 0644 /var/brain/infra/ec2/caddy/brain-caddy.service /etc/systemd/system/
sudo install -m 0644 /var/brain/infra/ec2/caddy/Caddyfile /etc/caddy/Caddyfile
sudo tee /etc/caddy/brain.env > /dev/null <<EOF
BRAIN_HOST=brain-yogesh.duckdns.org
EOF
sudo chown root:caddy /etc/caddy/brain.env /etc/caddy/Caddyfile
sudo chmod 0640 /etc/caddy/brain.env
sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy
sudo systemctl disable --now caddy.service    # disable the default unit shipped by the package
sudo systemctl daemon-reload
sudo systemctl enable --now brain-caddy.service

# --- brain-web env + build ---
sudo mkdir -p /etc/brain
aws secretsmanager get-secret-value --secret-id brain/web_env --region us-west-2 \
  --query SecretString --output text | sudo tee /etc/brain/brain-web.env > /dev/null
sudo chown root:ubuntu /etc/brain/brain-web.env
sudo chmod 0640 /etc/brain/brain-web.env

cd /var/brain && git pull --rebase --autostash
cd /var/brain/apps/brain-core && uv sync
cd /var/brain/apps/brain-web && npm install --no-audit --no-fund && npx next build

# --- Restart with new bind addresses ---
sudo install -m 0644 /var/brain/infra/ec2/systemd/brain-core.service /etc/systemd/system/
sudo install -m 0644 /var/brain/infra/ec2/systemd/brain-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart brain-core brain-web
```

## 6. Smoke test

From the Mac:

```bash
curl -sS https://brain-yogesh.duckdns.org/api/health
# expect {"ok":true}
open https://brain-yogesh.duckdns.org
# Google OAuth gate → redirects to / (today dashboard)
```

From iPhone Safari: same URL, Google sign-in, land on today dashboard.

## What's NOT in this phase

- Whoop V2 OAuth seeding — separate step, see below.
- Rotating the `brain-terraform` IAM user to AWS SSO — still open as a
  cleanup task.
- Cron cutover from Mac launchd to EC2 — still Day 7.

## Whoop OAuth (5-minute manual, Mon morning)

1. Register a developer app at `https://developer.whoop.com`:
   - Scopes: `read:recovery read:sleep read:workout read:cycle read:profile offline`
   - Redirect URI: `http://localhost:8765/callback`
   - Save the client ID and client secret.

2. **On your Mac**, run the bootstrap helper (it opens the authorize URL in
   your browser, catches the redirect, exchanges the code, and writes
   `brain/whoop_oauth` to Secrets Manager):
   ```bash
   WHOOP_CLIENT_ID=<id> WHOOP_CLIENT_SECRET=<secret> AWS_PROFILE=brain \
     python3 .scripts/whoop-oauth-bootstrap.py
   ```

3. Add the client credentials to brain-core's env on EC2 (via SSM):
   ```bash
   sudo tee -a /etc/brain/brain-core.env > /dev/null <<EOF
   BRAIN_WHOOP_CLIENT_ID=<client id>
   BRAIN_WHOOP_CLIENT_SECRET=<client secret>
   EOF
   sudo systemctl restart brain-core
   ```

Once seeded, `apps/brain-core/brain_core/whoop.py` picks up the creds from
Secrets Manager on every call and rotates refresh tokens back into the same
secret when Whoop issues a new one.
