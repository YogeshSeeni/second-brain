# 0007 — Worker container rides on Claude Code subscription, not API key

**Status:** Accepted — mount model revised 2026-04-14 (see Revision below)
**Date:** 2026-04-13
**Deciders:** Yogesh Seenichamy

## Context
The original Phase E sketch in the brain-v1 spec assumed the sandboxed `brain-worker:v1` container would authenticate to Anthropic with an `ANTHROPIC_API_KEY` pulled from AWS Secrets Manager. That works, but every token of every run would bill the metered API on top of the $20/mo Claude Code subscription Yogesh already pays for. The subscription is the resource that has slack — the API budget does not.

The host already runs `sync-claude-creds.sh` on a 5-minute systemd timer, pulling the OAuth token blob from `brain/claude_credentials` in Secrets Manager into `/home/ubuntu/.claude/.credentials.json` and pushing refreshed tokens back. This is the same loop the original control-panel build uses for its bare-metal `claude -p` invocations (#34). All the sandbox needs is a way to hand that file to the container.

## Decision
Bind-mount the host's Claude OAuth credentials file into every worker container, read-only, at a fixed in-container path, and steer `HOME` at it so `claude -p` finds it without any code change inside the sandbox.

Concretely, `build_docker_run_args` adds:

```
--mount type=bind,src=<host-creds>,dst=/claude-home/.claude/.credentials.json,readonly
-e HOME=/claude-home
```

The host path comes from `BRAIN_CLAUDE_CREDS` (default `/home/ubuntu/.claude/.credentials.json`) and is exposed as the `CLAUDE_CREDENTIALS` module constant in `lifecycle.py` next to `BARE_REPO`/`WORKTREE_ROOT`. `lifecycle.execute()` passes it through to `start_run()` on every invocation.

A separate, dedicated mount path (`/claude-home/`) is used instead of `/home/ubuntu/` because the container runs under the host UID with no matching `/etc/passwd` entry, so HOME is unset by default and the `/home/ubuntu` directory may not exist inside the image.

## Alternatives considered
- **`ANTHROPIC_API_KEY` from Secrets Manager.** Rejected: bills the metered API on top of the subscription Yogesh already pays for; adds a second credential to rotate; loses the per-account context (rate limits, history) that the OAuth path keeps.
- **Bind-mount the parent directory `/home/ubuntu/.claude/`.** Rejected: would expose any other dotfiles in `~/.claude/` to the sandboxed agent, weakening the trust boundary that the rest of the sandbox design works hard to maintain. The single-file mount is strictly less powerful.
- **Read-write mount so the container can refresh tokens itself.** Rejected: the host-side `claude-creds-sync.timer` is already the source of truth for token refresh, and a container writing back would race the host sync. Single-writer is simpler and our run lifetimes (~minutes) are well below token TTL.
- **Inject the token blob via env var.** Rejected: `claude` reads from the credentials file, not env; we would need a wrapper inside the image to materialize the file at startup. The mount path requires zero image changes.

## Consequences
### Positive
- Zero metered API spend for normal worker runs — they ride on the subscription
- Reuses the existing `claude-creds-sync.timer` infrastructure verbatim; no new secret to rotate
- No image change required: the existing `run-agent.sh` `claude -p` call works as-is
- Single-file mount preserves the principle that the sandbox sees only what it strictly needs
### Negative
- The dispatch host is now load-bearing for credential availability — if the timer falls behind and the token expires, every new run fails fast with an auth error (mitigated: `lifecycle.execute()` already returns FAILED outcomes cleanly per ADR-implicit Phase D leak fix, so the failure mode is observable in `brain_runs_total{state="failed"}` rather than silent corruption)
- Read-only mount means token refresh must happen on the host before the in-container token expires; bench loops that submit faster than the timer's 5-minute cadence inherit the same token across all runs (acceptable — token TTL >> 5 min)
- Sandbox boundary now depends on `cap_drop=ALL` + `no-new-privileges` to ensure the container can't escalate and read other host files; this was already true but the credentials mount makes the assumption load-bearing
### Neutral
- The default host path (`/home/ubuntu/.claude/.credentials.json`) is opinionated for the EC2 deployment; dev environments override via `BRAIN_CLAUDE_CREDS`
- `CLAUDE_CREDENTIALS` joins the existing module-constant pattern (`BARE_REPO`, `WORKTREE_ROOT`, `SCRATCH_ROOT`, `WORKER_IMAGE`) — when Phase E gets to per-host config files this graduates to a proper config object

## Revision 2026-04-14 — per-run writable claude-home, copy-back on success

The original single-file read-only mount turned out to be **incompatible with the claude CLI runtime**, discovered during the first real end-to-end smoke test (run_id `feb3a873-d89e-49ec-b1e0-09de803c4833`, instance `i-0a8d3c48265333a65`). Two independent reasons:

1. **Claude needs a writable `~/.claude/` for session state.** On every invocation the CLI writes `~/.claude.json`, `~/.claude/projects/<cwd>/<session>.jsonl`, and `~/.claude/backups/`. A read-only single-file mount leaves the parent directory unwritable. The process does not fail loudly — it blocks in an internal retry/lock loop (observed host-side as `wchan=ep_poll`, no open sockets, 0 CPU time, no stdout) until the run's 180 s timeout fires. Reproduced with a tmpfs `/claude-home` + readonly creds overlay.
2. **Claude refreshes OAuth tokens in-process.** Real subscription auth uses rotating refresh tokens; every run can rotate the token pair. A read-only mount forces a refresh attempt to fail silently. Observationally, our host creds expired ~1 day before the smoke test, and the hung container was actually trying (and failing) to refresh them. The original ADR assumption that "token refresh is handled host-side by the systemd `claude-creds-sync.timer`" was wrong — the timer is **push-only** (host→Secrets Manager), it does not refresh. In-container refresh is the only refresh that happens.

### Revised mount model
`lifecycle.execute()` now materializes a **per-run writable `claude-home` scratch** under the run's existing scratch directory (`{SCRATCH_ROOT}/run-<id>/claude-home/.claude/`), copies the host `CLAUDE_CREDENTIALS` file into it, and bind-mounts that directory RW at `/claude-home` in the container. After a successful run (`exit_code == 0`), the refreshed creds file is atomically copied back to the canonical host path via `os.replace`. `reap_run()` already deletes the scratch dir, so per-run isolation is automatic.

```
--mount type=bind,src=<scratch>/run-<id>/claude-home,dst=/claude-home
-e HOME=/claude-home
```

The host-side `claude-creds-sync.timer` still pushes any host changes to Secrets Manager on its 5-minute cadence — it just observes refreshes that came from the container instead of refreshes that came from a bare-metal `claude -p`. Semantics for external observers (EC2 spot rotation → bootstrap.sh pulls from Secrets Manager) are unchanged.

### Why this preserves the sandbox boundary
- The container still only sees a `.credentials.json` file under its isolated `/claude-home`, nothing else from the host's real `~/.claude/`.
- The scratch dir lives under `SCRATCH_ROOT`, which is already subject to `reap_run` cleanup — no long-lived writable state escapes the run.
- `cap_drop=ALL` + `no-new-privileges` + uid 1000 still prevent escalation to other host files.
- Concurrent runs do not share a claude-home: each gets its own scratch.

### Concurrency note
Two concurrent runs will each refresh the same starting refresh token. Whoever copies back first wins; the loser silently overwrites the winner on `os.replace`. In practice we expect the last-writer-wins semantics to match the host-side serialized behavior well enough for W1 bench loops — if rotation rate ever outpaces run concurrency we will add a file lock around `_propagate_refreshed_creds`.

### Rejected option — drop subscription for API key
Briefly reconsidered during debugging: would avoid the entire refresh-token rotation surface. Still rejected for the same reason as the original: metered spend, second credential to rotate. The writable-home fix is ~30 lines of Python.
