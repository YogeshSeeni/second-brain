#!/usr/bin/env bash
# Container entrypoint — receives prompt + metadata via env vars and exec's
# claude -p with stream-json output. stdout is captured by the host.
set -euo pipefail

: "${BRAIN_RUN_ID:?BRAIN_RUN_ID is required}"
: "${BRAIN_PROMPT:?BRAIN_PROMPT is required}"
: "${BRAIN_MODEL:=claude-sonnet-4-6}"

# cwd is /workspace — set by the Dockerfile WORKDIR. We don't pass --cwd
# to claude because that flag doesn't exist; the working directory is
# inherited from the process, and the bind-mounted worktree is at /workspace.
# --verbose is required by claude >= 2.x whenever --print is combined with
# --output-format=stream-json. Omitting it makes the CLI exit 1 immediately
# with: "When using --print, --output-format=stream-json requires --verbose".
exec claude -p "$BRAIN_PROMPT" \
  --model "$BRAIN_MODEL" \
  --output-format stream-json \
  --verbose \
  --include-partial-messages \
  --dangerously-skip-permissions
