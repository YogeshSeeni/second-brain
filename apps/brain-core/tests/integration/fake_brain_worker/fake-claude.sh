#!/usr/bin/env bash
# Mimics the subset of `claude -p --output-format stream-json` that
# sandbox/exec.py cares about. Writes one file into the worktree so the
# reconciler has something to fast-forward.
set -euo pipefail

echo '{"type":"message_start","message":{"id":"m1"}}'
echo '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"hello "}}}'
echo '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"world"}}}'

cd /workspace
printf 'run: %s\nfake: yes\n' "${BRAIN_RUN_ID:-unknown}" > fake-output.md
git -c user.email=t@t -c user.name=t add fake-output.md
git -c user.email=t@t -c user.name=t commit -qm "agent: ${BRAIN_RUN_ID:-unknown} — fake run"

echo '{"type":"result","result":"hello world","usage":{"input_tokens":10,"output_tokens":2,"cache_read_input_tokens":5,"cache_creation_input_tokens":0}}'
