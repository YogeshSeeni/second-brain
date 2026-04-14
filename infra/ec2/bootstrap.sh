#!/usr/bin/env bash
# brain-v1 app-layer bootstrap. Runs on every boot after cloud-init has
# attached + mounted the persistent brain-state volume to /var/brain.
#
# Idempotent: every step checks "already done?" before acting, so running
# twice on a warm box is a no-op and running on a fresh spot replacement
# rebuilds only the ephemeral pieces (creds, env file, systemd units,
# docker image, network) while leaving the persistent repo / venv / DB /
# vault.git alone.
#
# Invoked from cloud-init runcmd as:
#   sudo bash /var/brain/infra/ec2/bootstrap.sh
#
# Also safe to run by hand via SSM for recovery.

set -euo pipefail

log() { printf '[bootstrap %s] %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
fail() { log "FAIL: $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "must run as root"

REPO=/var/brain
AWS_REGION=${AWS_REGION:-us-west-2}
CLAUDE_SECRET=brain/claude_credentials
CREDS_PATH=/home/ubuntu/.claude/.credentials.json
ENV_FILE=/etc/brain/brain-core.env
WORKER_IMAGE=brain-worker:v1
VAULT_KEY_SECRET=brain/vault_deploy_key
VAULT_KEY_PATH=/home/ubuntu/.ssh/second-brain-vault
VAULT_SSH_HOST=github.com-vault
VAULT_REPO_URL="git@${VAULT_SSH_HOST}:YogeshSeeni/second-brain-vault.git"
VAULT_DATA_DIR=$REPO/vault-data

[ -d "$REPO/.git" ] || fail "$REPO is not a git checkout — cloud-init mount step must run first"

# ---------------------------------------------------------------- tools
log "ensuring awscli v2 is installed"
if ! command -v aws >/dev/null 2>&1; then
  ARCH=$(uname -m)
  case "$ARCH" in
    aarch64) AWS_URL=https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip ;;
    x86_64)  AWS_URL=https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip ;;
    *) fail "unsupported arch $ARCH" ;;
  esac
  tmpdir=$(mktemp -d)
  ( cd "$tmpdir" && curl -fsSL "$AWS_URL" -o awscliv2.zip && unzip -q awscliv2.zip && ./aws/install )
  rm -rf "$tmpdir"
fi
command -v aws >/dev/null 2>&1 || fail "aws install failed"

log "ensuring uv is installed"
if ! sudo -u ubuntu test -x /home/ubuntu/.local/bin/uv; then
  sudo -u ubuntu bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi
sudo -u ubuntu test -x /home/ubuntu/.local/bin/uv || fail "uv install failed"

# ---------------------------------------------------------------- repo sync
# Only pull if the working tree is clean — don't clobber in-progress work.
log "fetching repo updates (non-destructive)"
sudo -u ubuntu git -C "$REPO" fetch --all --quiet || log "git fetch failed (non-fatal)"

# ---------------------------------------------------------------- venv
log "ensuring brain-core venv exists and deps are synced"
sudo -u ubuntu bash -lc "cd $REPO/apps/brain-core && /home/ubuntu/.local/bin/uv sync --quiet" \
  || fail "uv sync failed"
sudo -u ubuntu test -x "$REPO/apps/brain-core/.venv/bin/python" || fail "venv python missing after sync"

# ---------------------------------------------------------------- claude creds
log "bootstrapping claude credentials from Secrets Manager"
install -d -o ubuntu -g ubuntu -m 700 /home/ubuntu/.claude
CREDS_JSON=$(aws --region "$AWS_REGION" secretsmanager get-secret-value \
  --secret-id "$CLAUDE_SECRET" --query SecretString --output text) \
  || fail "failed to fetch $CLAUDE_SECRET"
printf '%s' "$CREDS_JSON" | install -o ubuntu -g ubuntu -m 600 /dev/stdin "$CREDS_PATH"
# Validate
sudo -u ubuntu python3 -c "import json; json.load(open('$CREDS_PATH'))" \
  || fail "credentials file is not valid JSON"

# ---------------------------------------------------------------- vault deploy key
log "bootstrapping vault deploy key from Secrets Manager"
install -d -o ubuntu -g ubuntu -m 700 /home/ubuntu/.ssh
VAULT_KEY=$(aws --region "$AWS_REGION" secretsmanager get-secret-value \
  --secret-id "$VAULT_KEY_SECRET" --query SecretString --output text) \
  || fail "failed to fetch $VAULT_KEY_SECRET"
printf '%s' "$VAULT_KEY" | install -o ubuntu -g ubuntu -m 600 /dev/stdin "$VAULT_KEY_PATH"
# Trailing newline is required by OpenSSH key parsers.
case "$VAULT_KEY" in *$'\n') :;; *) printf '\n' >> "$VAULT_KEY_PATH" ;; esac
sudo -u ubuntu ssh-keygen -y -f "$VAULT_KEY_PATH" >/dev/null \
  || fail "vault deploy key is not a valid SSH key"

log "ensuring ssh config Host stanza for $VAULT_SSH_HOST"
SSH_CONFIG=/home/ubuntu/.ssh/config
install -o ubuntu -g ubuntu -m 600 /dev/null "$SSH_CONFIG.tmp"
# Strip any prior stanza for this host, then re-append a clean one.
if [ -f "$SSH_CONFIG" ]; then
  awk -v host="$VAULT_SSH_HOST" '
    BEGIN { skip=0 }
    /^Host[[:space:]]/ { skip = ($2 == host) ? 1 : 0 }
    skip==0 { print }
  ' "$SSH_CONFIG" > "$SSH_CONFIG.tmp"
fi
cat >> "$SSH_CONFIG.tmp" <<EOF
Host $VAULT_SSH_HOST
  HostName github.com
  User git
  IdentityFile $VAULT_KEY_PATH
  IdentitiesOnly yes
EOF
install -o ubuntu -g ubuntu -m 600 "$SSH_CONFIG.tmp" "$SSH_CONFIG"
rm -f "$SSH_CONFIG.tmp"

# Pre-accept GitHub host key so first clone doesn't prompt.
sudo -u ubuntu ssh-keyscan -t ed25519,ecdsa,rsa github.com 2>/dev/null \
  | sudo -u ubuntu tee -a /home/ubuntu/.ssh/known_hosts >/dev/null || true
sudo -u ubuntu sort -u -o /home/ubuntu/.ssh/known_hosts /home/ubuntu/.ssh/known_hosts

# ---------------------------------------------------------------- vault clone
log "ensuring vault clone at $VAULT_DATA_DIR"
if [ ! -d "$VAULT_DATA_DIR/.git" ]; then
  sudo -u ubuntu git clone --quiet "$VAULT_REPO_URL" "$VAULT_DATA_DIR" \
    || fail "vault clone failed"
else
  sudo -u ubuntu git -C "$VAULT_DATA_DIR" fetch --all --quiet \
    && sudo -u ubuntu git -C "$VAULT_DATA_DIR" pull --ff-only --quiet \
    || log "vault pull failed (non-fatal — timer will retry)"
fi

log "ensuring $REPO/wiki and $REPO/raw symlinks into vault-data"
for sub in wiki raw; do
  target="$VAULT_DATA_DIR/$sub"
  link="$REPO/$sub"
  if [ -L "$link" ]; then
    [ "$(readlink -f "$link")" = "$(readlink -f "$target")" ] && continue
    rm "$link"
  elif [ -e "$link" ]; then
    fail "$link exists and is not a symlink — refusing to clobber"
  fi
  sudo -u ubuntu ln -s "$target" "$link"
done

# ---------------------------------------------------------------- env file
log "writing $ENV_FILE"
install -d -m 755 /etc/brain
cat > "$ENV_FILE" <<EOF
# Written by bootstrap.sh — do not edit by hand
BRAIN_WORKER_IMAGE=$WORKER_IMAGE
BRAIN_CLAUDE_CREDS=$CREDS_PATH
AWS_REGION=$AWS_REGION
EOF
chown root:ubuntu "$ENV_FILE"
chmod 640 "$ENV_FILE"

# ---------------------------------------------------------------- systemd units
log "installing systemd units"
UNIT_SRC="$REPO/infra/ec2/systemd"
for unit in brain-core.service claude-creds-sync.service claude-creds-sync.timer \
            vault-sync.service vault-sync.timer; do
  install -m 644 "$UNIT_SRC/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload

# ---------------------------------------------------------------- docker network
log "ensuring docker network brain-runs exists"
if ! docker network inspect brain-runs >/dev/null 2>&1; then
  docker network create brain-runs
fi

# ---------------------------------------------------------------- worker image
log "building $WORKER_IMAGE if missing"
if ! docker image inspect "$WORKER_IMAGE" >/dev/null 2>&1; then
  ( cd "$REPO/infra/docker/brain-worker" && docker build --platform linux/arm64 -t "$WORKER_IMAGE" . )
fi

# ---------------------------------------------------------------- services
log "enabling + starting brain-core + claude-creds-sync + vault-sync"
systemctl enable --now claude-creds-sync.timer
systemctl enable --now vault-sync.timer
systemctl enable --now brain-core.service

# Give brain-core a moment to come up, then verify /metrics responds.
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8000/metrics >/dev/null 2>&1; then
    log "brain-core /metrics responding"
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8000/metrics >/dev/null 2>&1 \
  || log "WARNING: brain-core /metrics not responding after 10s — check journalctl -u brain-core"

log "bootstrap complete"
