# Module map — brain-v1

Living document: updated whenever a module lands, a boundary moves, or a file grows too large to read in one sitting.

## apps/brain-core/brain_core/

| Module | Purpose | Owns | Depends on |
|---|---|---|---|
| `main.py` | FastAPI app + route handlers | HTTP surface, SSE fan-out | everything below |
| `db.py` | aiosqlite wrapper, migrations | threads/messages/nudges/run_queue tables | — |
| `scheduler/` | ingress → admission → dispatch loops | `run_queue` state transitions | `db`, `sandbox`, `observability` |
| `sandbox/` | per-run isolation via git worktree + docker run | lifecycle of a single run | `scheduler` (types only), `observability` |
| `reconciler/` | merge run branch → `worktrees/main/` | fast-forward + (Week 2) three-way + conflict drafts | `sandbox` (types), `db` |
| `observability/` | OTEL spans + Prom metrics + structlog logs | `@traced` and `@metered` decorators | — |
| `agent.py` | **legacy** v0 `claude -p` subprocess path | SSE for existing chat | `db`, `voice` |
| `tick.py` | 15-min periodic loop | tick signals + nudges | `gcal`, `gtasks`, `whoop` |
| `watcher.py` | filesystem observer | raw/wiki change nudges | `db` |
| `voice.py` | system prompt construction | pinned context injection | — |
| `dashboard.py` `thesis.py` `inbox.py` `capture.py` `jobs.py` | route-local helpers | page-specific state | `db` |
| `gcal.py` `gtasks.py` | (Week 2 — currently stubs) | Google API wrappers | `integrations/google_oauth` |
| `whoop.py` | Whoop V2 API + auto-refresh | Whoop signals | `db`, Secrets Manager |

## bench/

| Module | Purpose |
|---|---|
| `run.py` | harness entrypoint |
| `loadgen/profiles.py` | ramp / sustained / burst / mixed |
| `loadgen/generator.py` | async submitter |
| `report/render.py` | pulls queue metrics, writes markdown + PNG charts |

## Conventions

- **One responsibility per file.** If a file is doing two unrelated things, split it.
- **Pure modules get unit tests** (`scheduler/admission.py`, `reconciler/merge.py`). I/O modules get integration tests (`sandbox/container.py`).
- **Observability is decorator-driven.** New code paths get `@traced` + `@metered` at the module level, not hand-written spans.
- **SQLite migrations** live in `brain_core/migrations/NNNN_<slug>.sql` and run at startup via `db.run_migrations()`.
