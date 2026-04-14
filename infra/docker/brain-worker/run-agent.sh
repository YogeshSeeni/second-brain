#!/usr/bin/env bash
# Container entrypoint — receives prompt + metadata via env vars and exec's
# claude -p with stream-json output. stdout is captured by the host.
set -euo pipefail

: "${BRAIN_RUN_ID:?BRAIN_RUN_ID is required}"
: "${BRAIN_PROMPT:?BRAIN_PROMPT is required}"
: "${BRAIN_MODEL:=claude-sonnet-4-6}"

exec claude -p "$BRAIN_PROMPT" \
  --model "$BRAIN_MODEL" \
  --output-format stream-json \
  --include-partial-messages \
  --dangerously-skip-permissions \
  --cwd /workspace
