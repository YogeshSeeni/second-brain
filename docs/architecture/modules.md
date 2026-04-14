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

## Status — Week 1 (tag `v1.0-foundations`)

| Module | State | Test coverage |
|---|---|---|
| `scheduler/types.py` | done | — |
| `scheduler/queue.py` | done | unit (5) |
| `scheduler/submit.py` | done | unit (4) |
| `scheduler/admission.py` | W1 stub (concurrency cap) | unit (3) |
| `scheduler/dispatch.py` | done | unit (1) |
| `scheduler/runner.py` | done | smoke |
| `scheduler/run_one.py` | done | integration (e2e) |
| `sandbox/types.py` | done | — |
| `sandbox/worktree.py` | done | unit (3) |
| `sandbox/container.py` | done (bare-repo bind-mount) | unit (arg construction) |
| `sandbox/exec.py` | done | unit (2) |
| `sandbox/lifecycle.py` | done | integration (via run_one) |
| `reconciler/merge.py` | done (fast-forward only) | unit (3) |
| `reconciler/three_way.py` | not started — W2 | — |
| `reconciler/conflicts.py` | not started — W2 | — |
| `observability/*` | not started — W1 ships without spans/metrics | — |
| `bench/run.py` | done (sustained profile only) | manual baseline |
| `bench/report/render.py` | done (local SQLite; Grafana query W3) | — |

### W1 baseline (60s, c=4, fake worker, M-series Mac)
- 21,411 submissions, 69 done, 546 conflicted, 3 failed
- avg latency 866 ms, p95 ≈ 1000 ms
- Conflict rate is expected: every branch is created from the same head commit, so only the first to fast-forward wins. Every other run stays on its branch for the W2 three-way merge path.
- Real Anthropic-call baseline lands in W3 once the API path is wired through.

### Known gaps (to resolve in W2)
- No real admission controller — cap-only stub
- No placement — FIFO over whichever container is free
- No observability emission — spans + metrics land in W2
- `main.py` still wires the legacy `agent.py` path for chat; chat-via-scheduler is a W2 task
- `transition_state` doesn't persist `error_class` / `error_detail` / `exit_code` from `RunOutcome` — failure rows are state-only until W2
- Fast-forward-only reconciler means parallel runs from the same head produce many CONFLICTED rows — three-way merge in W2 will recover most of them
