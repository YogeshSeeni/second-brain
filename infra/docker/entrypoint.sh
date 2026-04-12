#!/bin/bash
# entrypoint.sh — runs at container start.
# Responsibilities:
#   1. Pull secrets from AWS Secrets Manager into env + .credentials.json
#   2. Ensure /var/brain is a clone of the vault repo
#   3. Configure git user for auto-commits
#   4. Render the crontab template into /etc/cron.d/brain
#   5. Exec the CMD (default: cron -f)

set -euo pipefail

REGION="${AWS_REGION:-us-west-2}"
VAULT_DIR="/var/brain"
BRAIN_HOME="/home/runner"
CLAUDE_DIR="$BRAIN_HOME/.claude"
SECRETS_DIR="/run/secrets"

log() { echo "[entrypoint $(date -Is)] $*"; }

fetch_secret() {
    local name="$1"
    aws secretsmanager get-secret-value \
        --region "$REGION" \
        --secret-id "$name" \
        --query SecretString \
        --output text 2>/dev/null || true
}

mkdir -p "$SECRETS_DIR" "$CLAUDE_DIR"

log "fetching secrets from brain/*"
GITHUB_PAT="$(fetch_secret brain/github_pat)"
NTFY_TOPIC="$(fetch_secret brain/ntfy_topic || echo brain-yogesh)"
CLAUDE_CREDS="$(fetch_secret brain/claude_credentials || true)"
ANTHROPIC_API_KEY="$(fetch_secret brain/anthropic_api_key || true)"

# 1) Claude auth — prefer pre-copied OAuth creds, fall back to API key env.
if [[ -n "$CLAUDE_CREDS" ]]; then
    echo "$CLAUDE_CREDS" > "$CLAUDE_DIR/.credentials.json"
    chown runner:runner "$CLAUDE_DIR/.credentials.json"
    chmod 600 "$CLAUDE_DIR/.credentials.json"
    log "wrote claude oauth credentials"
elif [[ -n "$ANTHROPIC_API_KEY" ]]; then
    echo "export ANTHROPIC_API_KEY='$ANTHROPIC_API_KEY'" > "$SECRETS_DIR/anthropic.env"
    chown runner:runner "$SECRETS_DIR/anthropic.env"
    chmod 600 "$SECRETS_DIR/anthropic.env"
    log "using ANTHROPIC_API_KEY fallback"
else
    log "WARNING: no claude credentials found — interactive 'claude login' required"
fi

# 2) ntfy topic file so .scripts/notify.sh picks it up
echo "$NTFY_TOPIC" > "$SECRETS_DIR/ntfy_topic"
chmod 644 "$SECRETS_DIR/ntfy_topic"

# 3) Vault clone / pull
if [[ ! -d "$VAULT_DIR/.git" ]]; then
    if [[ -z "$GITHUB_PAT" ]]; then
        log "ERROR: vault not cloned and brain/github_pat is empty — cannot proceed"
        exit 1
    fi
    log "cloning vault into $VAULT_DIR"
    cd /tmp
    git clone "https://x-access-token:${GITHUB_PAT}@github.com/YogeshSeeni/second-brain.git" "$VAULT_DIR"
    chown -R runner:runner "$VAULT_DIR"
else
    log "vault already cloned, pulling latest"
    cd "$VAULT_DIR"
    sudo -u runner git pull --rebase --autostash origin main || log "git pull failed (non-fatal)"
fi

# Persist GITHUB_PAT in the remote URL so runner pushes work without token prompts
cd "$VAULT_DIR"
if [[ -n "$GITHUB_PAT" ]]; then
    sudo -u runner git remote set-url origin "https://x-access-token:${GITHUB_PAT}@github.com/YogeshSeeni/second-brain.git"
    sudo -u runner git config user.email "assistant@brain.local"
    sudo -u runner git config user.name "brain-assistant"
fi

# 4) Render crontab — copy template with env expanded
if [[ -f "$VAULT_DIR/.scripts/cron/crontab.template" ]]; then
    log "installing crontab"
    envsubst < "$VAULT_DIR/.scripts/cron/crontab.template" > /etc/cron.d/brain
    chmod 0644 /etc/cron.d/brain
    # system cron on debian wants crontab files to end with a newline
    echo "" >> /etc/cron.d/brain
else
    log "WARNING: no crontab template at $VAULT_DIR/.scripts/cron/crontab.template"
fi

# Point notify.sh at the right ntfy topic via state file
install -d -o runner -g runner "$VAULT_DIR/.scripts/state"
echo "$NTFY_TOPIC" > "$VAULT_DIR/.scripts/state/ntfy_topic"
chown runner:runner "$VAULT_DIR/.scripts/state/ntfy_topic"

log "ready; exec: $*"
exec "$@"
