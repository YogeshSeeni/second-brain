# brain-core

FastAPI orchestrator that spawns `claude -p` subprocesses, streams output to
SSE clients, persists chat state in SQLite, watches the vault filesystem, and
polls Google Calendar + Google Tasks on a 15-min tick.

## Environment

| Var | Default | Purpose |
|---|---|---|
| `BRAIN_DB_PATH` | `./db/brain.sqlite` | SQLite file. Prod uses `/var/brain/db/brain.sqlite`. |
| `BRAIN_VAULT_PATH` | `/Users/yogeshseenichamy/second-brain` | Vault root used to load `CLAUDE.md`, `wiki/voice.md`, and `wiki/thesis/*`. |
| `CLAUDE_BIN` | `claude` | Path to the `claude` CLI. |

## Local dev

```bash
cd apps/brain-core
uv sync
uv run uvicorn brain_core.main:app --reload --port 8000
```

Smoke test:

```bash
curl -s http://localhost:8000/api/health
```

Chat round-trip (requires `claude` on PATH):

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"thread_id": null, "body": "hello"}'
# → {"task_id": 1, "thread_id": "..."}

curl -N http://localhost:8000/api/chat/stream/1
```
