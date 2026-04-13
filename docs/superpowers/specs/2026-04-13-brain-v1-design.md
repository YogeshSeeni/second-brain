# brain-v1 — Design Document

**Status:** Approved (brainstorm). Awaiting implementation plan.
**Date:** 2026-04-13
**Author:** Yogesh Seenichamy (with Claude)
**Supersedes:** `~/.claude/plans/gentle-percolating-pine.md` (the v0 1-week plan)
**Timeline:** 4 weeks · 2026-04-14 → 2026-05-11
**Infra target cost:** ~$15/month on AWS Spot

---

## 1. Context

### 1.1 What v0 is

`brain v0` is a Claude-Code-powered "second brain" over an Obsidian-style markdown vault. It consists of:

- `apps/brain-core` — FastAPI backend that spawns `claude -p` subprocesses to run agent turns, streams their output over SSE, persists threads and messages in SQLite, watches the vault filesystem, runs a 15-minute tick loop, exposes endpoints for chat, capture, jobs, inbox, thesis, and dashboard.
- `apps/brain-web` — Next.js 16 + Tailwind v4 control panel with a persistent shell, chat workspace, dashboard, capture page, jobs table, inbox drafts, thesis axes, and wiki browser.
- A bare-metal cron at `/etc/cron.d/brain` on a `t4g.small` EC2 instance in `us-west-2`, reachable at `brain-yseenich.duckdns.org` behind Caddy + NextAuth Google OAuth.
- Nine job prompts in `jobs/` (morning, evening, whoop-pull, weekly-review, lint, lc-daily, arxiv-digest, canvas-sync, recruiting-prep), each runnable via `.scripts/run-job.sh --job <name>`.
- A working Whoop V2 OAuth integration with auto-refresh against AWS Secrets Manager.

As of 2026-04-13, v0's Phase 0 / A / B / Days 2–6 have shipped. The first unattended cron fire is 2026-04-14 06:00 PDT.

### 1.2 Why v1

Three things are wrong with v0 for the goal it's trying to reach:

1. **Google Calendar and Google Tasks are stubs.** `gcal.py` and `gtasks.py` return `{"skipped": "Day 3+"}`. The tick loop knows they exist; nothing works.
2. **Agents run bare-metal as `claude -p` subprocesses with unrestricted vault RW.** Fine for one agent. Breaks down the moment you want concurrent agents, per-agent isolation, conflict-aware merging, or any form of "launch an agent against a scoped view of the wiki and hand it off."
3. **The system has no story.** v0 is engineering-adjacent plumbing. There's no benchmark, no metrics under load, no characterization, no numbers to cite in an interview. A side project without numbers reads as a hobby.

v1 fixes all three, treating the project as a month-long portfolio piece aimed at quant-infra interviews (Citadel / Virtu / Plaid / Jane Street) and a technical blog post authored, in part, by the system itself.

### 1.3 Goals

- **Ship real Google Tasks + Calendar integration** with an autonomy policy that auto-executes low-stakes actions and routes high-stakes ones to a review inbox.
- **Run agents in isolated per-run git-worktree sandboxes** with conflict-aware reconciliation back to `main`. Safely support 10–20 concurrent agents on a single node.
- **Build a custom single-node scheduler** with token-budget admission control and prompt-cache-aware placement, because the bottleneck for Claude workloads is the Anthropic API budget, not CPU.
- **Instrument everything** through OpenTelemetry + Prometheus, with a benchmark harness that produces weekly reports tracking a single north-star metric: **prompt cache hit ratio**.
- **Ship a responsive control panel** that is the only user-facing surface. Everything — OAuth bootstrap, autonomy toggles, cron edits, scheduler tuning, run monitoring, benchmark viewing — lives in the web UI. Aesthetic: clean, sleek, minimalist, Linear/Vercel/Stripe family. Not AI-slop.
- **Run cheap.** ~$15/month on t4g.large Spot + Grafana Cloud free tier + SQLite-backed queue.
- **Produce concrete artifacts:** a live URL, a design doc, a decision log, weekly benchmark reports, four Grafana Cloud dashboards, and a technical blog post the system writes about itself as its graduation test.

### 1.4 Non-goals

- Multi-user support. Yogesh is the only user. No authentication beyond the existing Google OAuth allowlist.
- Horizontal scaling across a worker fleet. The story is depth on one node.
- Mid-run agent preemption. Agents finish or get SIGINT'd on Spot drain; no complex preemption semantics.
- Native mobile apps. Responsive web only. No PWA, no service worker, no iOS Shortcut, no Telegram bot (v1; all may be added later).
- High availability. Single instance + Spot interruption recovery is the reliability model. No multi-AZ failover.
- Real-time (<100ms) UX for agent operations. Claude API round-trips dominate anyway; the system optimizes for P95 ~1.3s agent turn latency, not millisecond-level responsiveness.

---

## 2. Decision Log

Every material choice in this design, with one-line rationale and reference to the section discussing it. When a mid-build decision changes one of these, an ADR lands in `docs/architecture/decisions/` and this log is updated.

| # | Decision | Rationale | Section |
|---|---|---|---|
| D1 | Single-worker on a single EC2 instance | Depth on one node is a stronger interview story than breadth across a fleet for this workload. | §3 |
| D2 | t4g.large ARM64 on AWS Spot | ~$15/month; ARM is cheaper; Spot + interruption handling is itself an interview story. | §3, §9 |
| D3 | EBS-persisted state + ASG(desired=1) for Spot recovery | State survives interruption; ASG replaces the instance in ~60s; systemd brings services back. | §9 |
| D4 | Grafana Cloud free tier for metrics/traces/logs | Saves ~1.5GB RAM and ops burden vs local Prometheus/Tempo/Grafana; ingest is free at this volume. | §8 |
| D5 | SQLite WAL mode as the job queue | Adequate for ~50 enqueues/min peak; avoids a Redis dependency; defensible under interview scrutiny. | §3, §4 |
| D6 | `claude -p` subprocess inside Docker container per run (vs long-lived exec'd containers) | Image layer caching makes `docker run` ~250ms, below the Anthropic API noise floor; avoids mount-namespace trickery. | §5 |
| D7 | Per-run git worktree off a bare `vault.git` repo | Natural isolation primitive; supports sparse-checkout for scoped runs; matches how git already models parallel work. | §5 |
| D8 | Conflict-aware reconciler: fast-forward → three-way → inbox draft | Conflicts become first-class human-review events instead of silent losses. | §5 |
| D9 | Scheduler is three async coroutines: ingress, admission, dispatch | Separating admission (API budget) from dispatch (container availability) makes bottlenecks observable. | §4 |
| D10 | Leaky-bucket admission over ITPM, OTPM, RPM | Actual Claude rate-limit dimensions; auto-tuned from `anthropic-ratelimit-*` response headers. | §4 |
| D11 | Weighted deficit round-robin across four agent classes (chat 50 / synth 30 / ingest 15 / background 5) | Work-conserving fair-share under contention; chat gets latency priority. | §4 |
| D12 | EWMA estimator per prompt family for admission reservations | Self-correcting within 3–5 runs; conservative seed avoids first-run over-admission. | §4 |
| D13 | Prompt-cache-aware placement with 5-minute affinity window | Anthropic's prompt cache is per-backend, ~5-minute TTL; same-family runs must pin to the same container to capture hits. | §4 |
| D14 | Five priority levels, no mid-run preemption, chat-interrupt-on-new-message kept as the one exception | Simpler semantics; avoids the "already paid for the tokens" preemption ambiguity. | §4 |
| D15 | Warm pool: image-cached pre-pulled containers, not long-lived exec'd containers | `docker run` cold-start is fast enough; avoids nsenter-style mount games. | §5 |
| D16 | Every agent invocation (including interactive chat) goes through `scheduler.submit()` | Single code path; chat runs at priority=CRITICAL with unbounded budget class. | §3 |
| D17 | `run-job.sh --direct` fallback kept in week 1, deleted in week 4 | Safety valve while the scheduler is unproven; removed once confidence is established. | §10 |
| D18 | Google OAuth shared between Calendar + Tasks in one consent flow | Single refresh token; simpler UX; stored in AWS Secrets Manager. | §6 |
| D19 | Local policy proxy inside the sandbox container for Google calls | Agents can't bypass the policy because the sandbox egress can't reach `*.googleapis.com` directly. | §6 |
| D20 | Autonomy policy split: in-vault auto-execute, external-attendee invites and non-self-authored changes draft-only | Safety boundary scoped to irreversibility of the action. | §6 |
| D21 | Provenance tag `—brain/<run_id>` on every agent-created Google object | Lets the tick differ identify agent-authored objects for autonomy decisions. | §6 |
| D22 | Ingest → Wiki → Output three-pillar IA framing | Karpathy LLM-wiki-inspired; visible in the sidebar grouping; URL routes (`/ingest`, `/wiki`, `/runs`) reflect the pillars. | §7 |
| D23 | 12 route groups; every feature controllable from the web control panel | The control panel is the only user-facing surface; no CLI bootstrap, no external apps. | §7 |
| D24 | Responsive web only; no PWA, no service worker, no native app | Complexity budget goes to infra, not mobile channels. | §7 |
| D25 | Visual language: zinc palette, one teal/indigo accent, Geist Sans + Geist Mono, typographic hierarchy | Linear/Vercel/Stripe family; explicitly not AI-slop. | §7 |
| D26 | OpenTelemetry OTLP HTTP exporter + Prometheus `/metrics` scraped by `grafana-agent` + structlog JSON to Loki | Buffered remote shipping via grafana-agent survives ingest disruption; HTTP OTLP is easier to debug than gRPC. | §8 |
| D27 | Decorator-driven instrumentation (`@traced`, `@metered`) | Callers stay clean; span + metric coverage is uniform across modules. | §8 |
| D28 | Five trace trees: agent run, tick, watcher, ingest, benchmark | Organized by "kind of thing the system does"; each trace has a stable root span. | §8 |
| D29 | North-star metric: `brain_anthropic_prompt_cache_hit_ratio` | Single number the interview story hinges on; measured at the point of truth (Anthropic response headers). | §8 |
| D30 | Benchmark harness at `bench/` producing weekly markdown reports | Turns "I built it" into "I measured it and improved it"; makes regressions detectable. | §8 |
| D31 | Four Grafana Cloud dashboards (overview, prompt cache analysis, scheduler trace, Spot resilience) | Dashboard-as-code via JSON in `infra/grafana/dashboards/`. | §8 |
| D32 | Poisoned-run mechanic: 3 failures in 24h → job marked `paused` until human re-enables | Prevents runaway token cost from a bad prompt. | §9 |
| D33 | Spot drain: 2-min metadata poll → 90s graceful drain → SIGINT + mark `interrupted` → fsync → shutdown; replacement instance re-enqueues interrupted runs at boot | Recoverable in ~5 minutes total with zero data loss. | §9 |
| D34 | Alerts route to in-app nudges, not PagerDuty/email | Yogesh isn't on-call; noise reduction. | §9 |
| D35 | Unit tests for load-bearing pure modules (admission, placement, reconciler, autonomy, drain); integration tests against a fake Anthropic server; one smoke test against prod; bench-as-test weekly | Strategic testing, not coverage-hunting; every load-bearing module has tests by week 4. | §10 |
| D36 | TDD not default; rule: "tests for last week's modules exist before this week's dependent work" | Moves fast in week 1; full coverage of critical paths by week 4. | §10 |
| D37 | Documentation discipline: Decision Log here + ADRs in `docs/architecture/decisions/` + living module map in `docs/architecture/modules.md` | Durable, repo-side record of every material choice. | §2, §11, §12 |
| D38 | `self-write-blog` graduation job: system reads its own git log, ADRs, bench reports, and design doc to author a technical blog post about itself | The system demonstrates it works by documenting itself. | §11 |
| D39 | Public read-only view at `/public/*` for bench reports and selected runs | Shareable URL for recruiters without needing allowlist access. | §11 |

**Out-of-scope choices** (intentionally not made, noted so future readers know they were considered): Firecracker microVMs (too expensive, wrong instance family), nsjail/bubblewrap (marginal gain over Docker, complexity cost), Rust scheduler rewrite (timeline risk), K8s/Nomad (multi-node, wrong scale), AWS Fargate (cold-start too slow, hides the interesting work), Redis Streams (SQLite is enough for this load), local Prometheus/Tempo/Grafana (replaced by Grafana Cloud free tier).

---

## 3. Architecture Overview

### 3.1 Topology

One EC2 `t4g.large` on Spot in `us-west-2`. Single node, single process per role, all services on the same host. Public ingress gated by Caddy + NextAuth Google OAuth; everything behind brain-web is internal.

```
                          ┌──────────────────────────────────────────────┐
                          │ t4g.large · us-west-2 · brain-v1 · Spot       │
                          │                                               │
iPhone/laptop ──► Caddy ──┼─► brain-web  (Next.js 16, responsive shell)  │
(OAuth gate)              │        │                                      │
                          │        └─SSE/HTTP─► brain-core  (FastAPI)     │
                          │                         │                     │
                          │                         ├─► Scheduler         │
                          │                         │       │             │
                          │                         │       ▼             │
                          │                         │   Warm Pool         │
                          │                         │       │             │
                          │                         │       ▼             │
                          │                         │   Sandbox (Docker)  │
                          │                         │       │             │
                          │                         │       ▼             │
                          │                         │   Reconciler (git)  │
                          │                         │                     │
                          │                         ├─► integrations/     │
                          │                         │     gcal.py         │
                          │                         │     gtasks.py       │
                          │                         │     whoop.py        │
                          │                         │     google_oauth.py │
                          │                         │                     │
                          │                         ├─► tick.py           │
                          │                         ├─► watcher.py        │
                          │                         ├─► ingest/           │
                          │                         ├─► inbox.py          │
                          │                         ├─► thesis.py         │
                          │                         ├─► dashboard.py      │
                          │                         ├─► autonomy.py       │
                          │                         ├─► spot/drain.py     │
                          │                         └─► observability/    │
                          │                                                │
                          │  State on EBS gp3 200GB:                       │
                          │    /var/brain/vault.git        (bare repo)     │
                          │    /var/brain/worktrees/main/  (live reader)   │
                          │    /var/brain/worktrees/run-*/ (per-run)       │
                          │    /var/brain/db/brain.sqlite  (WAL mode)      │
                          │    /var/brain/config/{policy,jobs}.{json,yaml} │
                          │    /var/brain/scratch/run-*/   (tmpfs intermed)│
                          │                                                │
                          │  Telemetry egress → Grafana Cloud free tier    │
                          │    grafana-agent (systemd)                     │
                          │      ├─ scrapes brain-core /metrics            │
                          │      ├─ receives OTLP on 127.0.0.1:4318        │
                          │      └─ tails structlog JSON via file input    │
                          └──────────────────────────────────────────────┘
```

### 3.2 Key shifts from v0

1. **Vault becomes a bare git repo.** `/var/brain/vault.git` is the ground truth. The live reader that brain-core reads from is just one worktree (`worktrees/main/`); every sandboxed agent run adds a new short-lived worktree (`worktrees/run-<uuid>/`). This is the most important structural change.
2. **Scheduler + Warm Pool + Reconciler are three new modules** inside brain-core, each owning one responsibility.
3. **SQLite queue replaces direct subprocess management.** Every agent invocation — chat, tick-fired, watcher-triggered, job — goes through `scheduler.submit()` and a durable queue.
4. **Google Calendar + Google Tasks become real.** Shared OAuth refresh flow against AWS Secrets Manager; HTTP clients against the Google REST APIs; autonomy policy enforced at a local proxy inside the sandbox.
5. **Observability stack is Grafana Cloud.** No local Prometheus, Tempo, or Grafana. `grafana-agent` is the only local telemetry process.
6. **Instance upgrade + Spot.** `t4g.small` on-demand → `t4g.large` on Spot, with EBS-persisted state and ASG-based replacement on interruption.

### 3.3 What v0 keeps

- `apps/brain-web` shell and existing pages (retrofitted to the new visual language).
- NextAuth Google OAuth allowlist, Caddy config, DuckDNS DNS.
- `watcher.py`, `nudges`, `capture` (renamed to `ingest`), `inbox`, `thesis`, `dashboard`, `whoop.py` internals.
- SQLite threads/messages/nudges schema (extended, not replaced).
- All nine job prompts in `jobs/`.
- `CLAUDE.md` wiki conventions.

### 3.4 What v0 retires

- Bare-metal `run-job.sh` direct-to-`claude -p` path. Becomes a thin HTTP client to brain-core's `/api/jobs/{name}/run`. A `--direct` fallback flag is kept in week 1 for safety and deleted in week 4.
- The dual-fire guard in `run-job.sh` is replaced by scheduler-level idempotency key deduplication.
- Stub `gcal.py` and `gtasks.py`.
- MCP-tool-call references in job prompts (`mcp__claude_ai_Google_Calendar__*`). Jobs now call the local policy proxy instead.

---

## 4. Scheduler

### 4.1 Three loops

The scheduler is three async coroutines inside brain-core's event loop, coordinating through SQLite and in-memory state.

**Ingress loop.** `scheduler.submit()` is the public entry point. Synchronous return to the caller, non-blocking operation. Inserts a `run_queue` row with status `pending`, estimated `(input_tokens, output_tokens)`, agent class, priority, prompt prefix family, and an idempotency key (hash of `(trigger_source, payload)` to dedupe duplicate submissions from tick/watcher). Emits span `scheduler.submit`. Returns `run_id` immediately.

**Admission loop.** Runs every 50ms. Reads pending runs ordered by `(priority DESC, created_at ASC)`, asks the admission controller if the next run can be admitted, moves it to `admitted` or leaves it. Batch-limited to 5 runs per tick. Emits span `scheduler.admission_pass` with queue depth and budget headroom attributes.

**Dispatch loop.** Runs every 20ms. Reads `admitted` runs, asks the placement module which warm container to assign, moves the run to `running`, calls `sandbox.start_run()`. Emits span `scheduler.dispatch` with chosen container and placement reason.

Separating admission from dispatch matters: admission is about API budget, dispatch is about container availability. Conflating them would lose visibility into which bottleneck is firing, and observable bottlenecks are the whole point of the instrumentation.

### 4.2 Admission controller

Three leaky buckets, one per rate-limit dimension: ITPM (input tokens/min), OTPM (output tokens/min), RPM (requests/min). Ceilings are auto-learned from `anthropic-ratelimit-*` response headers; seeded with conservative defaults (ITPM 400k, OTPM 80k, RPM 4000 for Sonnet 4.6 on Max 200).

Each bucket tracks a 60-second sliding window of actual consumed tokens from recent runs, plus reservations for runs that are admitted but not yet complete:

```
effective_usage = observed_last_60s + sum(reservations_for_running_runs)
headroom        = ceiling - effective_usage
```

A run with estimated cost `(est_in, est_out)` is admitted iff it fits in the remaining headroom of all three dimensions.

**Estimates.** EWMA of actual `(input_tokens, output_tokens)` per prompt family, seeded conservatively on first run. Self-corrects within 3–5 runs. Chat turns use a heuristic based on thread history length.

**Per-class quotas.** Four agent classes with fair-share weights under contention:
- `chat` — 50% (interactive latency priority)
- `synthesis` — 30%
- `ingest` — 15%
- `background` — 5%

Work-conserving: a class can use more than its quota if no other class is competing. Weighted deficit round-robin drives fair-share when classes compete.

**On completion**, the actual consumed tokens (from the final result event's `usage` block) replace the reservation. If the estimate was wrong, the bucket self-corrects within the window.

### 4.3 Placement — prompt-cache-aware

Anthropic's prompt cache is per-backend with a ~5-minute TTL. Randomly distributing runs across warm containers defeats the cache; the same prompt family must keep hitting the same container for cache warmth to accumulate.

Scoring:
1. `+100` if the container ran the same prompt family within the last 5 minutes
2. `+50` if within 10 minutes
3. `0` otherwise
4. `-50` if the container is currently busy
5. Pick the max-scored idle container
6. If no idle container, the run waits in the dispatch queue (not the admission queue — it's past admission)
7. Tie break: pick the oldest-idle container to maximize cache-eviction tolerance on others

This is the optimization that moves the north-star metric (`brain_anthropic_prompt_cache_hit_ratio`) from ~18% baseline to a target of 70%+.

### 4.4 Priorities and preemption

Five priority levels: `CRITICAL` (chat, urgent watcher nudges), `HIGH` (interactive `/jobs/{name}/run`), `NORMAL` (tick-fired runs), `LOW` (scheduled cron jobs), `BACKGROUND` (lint, arxiv-digest).

**No mid-run preemption.** Higher-priority runs jump the admission queue; running runs finish.

**Exception:** chat messages with `interrupt=true` (new message while a previous chat turn is mid-run) SIGINT the prior chat turn. Single-thread-scoped, not scheduler-level.

**Chat goes through scheduler.submit() like everything else** at `priority=CRITICAL` with an unbounded-budget class, so it skips admission-level backpressure but is still traced and metered uniformly.

### 4.5 What is not built (YAGNI)

- Scheduler HA (no Raft, no leader election; scheduler recovers from SQLite on restart)
- Cross-worker placement (single node)
- Predictive warm-pool scaling (static: `min=2, max=8, target_idle=2`)
- SLA-driven termination (no "must finish in 30s or kill")
- Fair-share across users (Yogesh is the only user)

---

## 5. Sandbox + Worktree Lifecycle

### 5.1 On-disk layout

```
/var/brain/
├── vault.git/              bare repo — single source of truth
├── worktrees/
│   ├── main/               long-lived worktree on branch `main`
│   │                       (brain-core route reads + watcher)
│   └── run-<uuid>/         short-lived per-run worktrees on branch `agent/run-<uuid>`
└── scratch/                tmpfs-ish per-run space for intermediates
    └── run-<uuid>/
```

The bare repo is ground truth. `worktrees/main/` is the live reader — no special privilege except that HTTP routes read from it.

### 5.2 Lifecycle of a run

```
[1] scheduler dispatch
[2] sandbox.prepare_run(run_id)     → WorktreeHandle
[3] sandbox.start_run(handle)        → container + claude -p
[4] sandbox.exec stream              → stream-json parsed, SSE fanned out, spans emitted
[5] claude -p exits                  → handle.exit_code, usage block captured
[6] reconciler.reconcile(run_id)     → fast-forward / three-way / conflict draft
[7] sandbox.reap_run(run_id)         → worktree torn down
[8] scheduler cleanup                → run state=done|failed|conflicted
```

**Step 2 — `prepare_run`.** Creates the worktree:

```bash
git -C /var/brain/vault.git worktree add --no-checkout \
    /var/brain/worktrees/run-<uuid> \
    -b agent/run-<uuid> main
git -C /var/brain/worktrees/run-<uuid> checkout agent/run-<uuid>
```

For runs with a declared `vault_scope` (e.g., "only needs `wiki/career/` and `wiki/thesis/`"), sparse-checkout is configured before the actual checkout. Scoped runs populate in ~80ms; full-vault runs in ~400ms. Creates a `run_worktrees` row.

**Step 3 — `start_run`.** Runs a container with the worktree bind-mounted:

```bash
docker run --rm \
    --cpus=1.0 --memory=512m --memory-swap=512m --pids-limit=256 \
    --network=brain-runs --security-opt no-new-privileges --cap-drop=ALL \
    --mount type=bind,src=/var/brain/worktrees/run-<uuid>,dst=/workspace \
    --mount type=bind,src=/var/brain/scratch/run-<uuid>,dst=/scratch \
    -e BRAIN_RUN_ID=<uuid> -e BRAIN_PROMPT_FAMILY=<family> \
    brain-worker:v1 \
    /usr/local/bin/run-agent.sh
```

The `brain-runs` docker network has no default route; `/etc/hosts` in the container resolves only the allowlist (`api.anthropic.com`, `calendar.googleapis.com`, `tasks.googleapis.com`, `api.prod.whoop.com`, `arxiv.org`, `github.com`, `127.0.0.1` for the local policy proxy).

Image cold-start is ~250ms on a warm host cache, which is below the Anthropic API noise floor.

**Step 4 — exec stream.** The container entrypoint runs:

```bash
claude -p "$PROMPT" \
    --model claude-sonnet-4-6 \
    --output-format stream-json \
    --include-partial-messages \
    --dangerously-skip-permissions \
    --cwd /workspace
```

Stream-json is captured by the host via the Docker SDK's `attach` API. Each event is parsed and routed to: chat SSE fan-out (if chat), span emitter, metrics collector, DB.

**Step 5 — exit handling.** Exit code, final `result` event, and `usage` block captured. These go to the reconciler even on failure.

**Step 6 — reconcile.** See §5.3.

**Step 7 — reap.** Removes the worktree directory, drops the `run_worktrees` row, cleans up scratch. Branch handling depends on reconcile status — merged runs get the branch deleted, conflicted runs keep the branch alive.

**Step 8 — scheduler cleanup.** Run state transitions. Admission controller reclaims the reservation with actual consumed tokens. Warm pool semaphore releases.

### 5.3 Reconciler

```
# inside the run's worktree
if uncommitted changes exist:
    git add -A
    git commit -m "agent: <run_id> — <agent_class> — <one-line prompt summary>"

# push branch back into the bare repo
git -C /var/brain/vault.git fetch . agent/run-<uuid>:agent/run-<uuid>

# try fast-forward merge on the live main worktree
cd /var/brain/worktrees/main
git merge --ff-only agent/run-<uuid>

if ff succeeded:
    status = "merged"
    delete branch agent/run-<uuid>
elif ff not possible:
    attempt three-way merge
    if three-way succeeds:
        status = "merged"
    else:
        status = "conflict"
        leave branch alive; file inbox draft
```

**Conflict drafts.** Generated at `wiki/ops/inbox/conflict-<run_id>.md` with the conflicted files, base/ours/theirs SHAs, rebase-style diff, link to the run's Grafana Cloud trace, and three actions in `/inbox`: **Accept theirs** (force-checkout the run's branch), **Accept ours** (abandon the branch), **Open in chat** (spawn a topic thread scoped to the conflict).

`git gc` is disabled on the bare repo to prevent the reflog from cleaning up unresolved branches.

### 5.4 Resource caps and isolation

Every container gets cgroup limits: 1 vCPU, 512 MB RAM, no swap, 256 pids, 1024 open files, dedicated docker network with no default route, `no-new-privileges`, all capabilities dropped.

### 5.5 Interview story

Per-run sandbox: agent operates on its own git worktree off a bare repo. Reconciler fast-forwards when possible, files conflicts as first-class inbox items when not. 20 agents in parallel without stepping on each other. Worktree creation <100ms for scoped runs via sparse-checkout; container start ~250ms from a pre-baked image; full lifecycle instrumented with OTEL spans end to end, visible as a flame graph per run.

---

## 6. Google Tasks + Calendar + Autonomy

### 6.1 Shared OAuth

Single OAuth flow covering both Calendar and Tasks in one consent screen. Scopes:
- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/tasks`

Bootstrap is browser-mediated through the control panel at `/settings/integrations/google`. "Connect Google Account" button POSTs to `/api/oauth/google/start`, which returns a Google consent URL. On callback at `/api/oauth/google/callback`, brain-core captures the refresh token and writes it to AWS Secrets Manager at `brain/google_oauth` as `{refresh_token, client_id, client_secret}`. Same pattern as the working Whoop bootstrap.

`integrations/google_oauth.py` owns the refresh dance. Shared by `gcal.py` and `gtasks.py`. Handles refresh-token rotation if Google returns a new one.

### 6.2 `gcal.py`

Thin wrapper on `calendar.googleapis.com/calendar/v3`. Methods:
- `list_events(time_min, time_max, calendar_id='primary')` → normalized dicts
- `get_event(event_id)`
- `create_event(summary, start, end, description=None, attendees=None)` → returns the created event
- `update_event(event_id, patch)`
- `delete_event(event_id)`
- `find_free_time(duration_min, search_start, search_end)` → scans busy blocks, returns candidate windows

Change detection reuses the existing `gcal_seen` table. Tick diffs emit signals (new event, deleted event, moved event, event-starting-soon, event-conflicts-with-task). Signals become nudges when interesting.

### 6.3 `gtasks.py`

Thin wrapper on `tasks.googleapis.com/tasks/v1`. Methods:
- `list_tasklists()`
- `list_tasks(tasklist_id='@default', show_completed=False, show_hidden=False)`
- `get_task(tasklist_id, task_id)`
- `insert_task(tasklist_id, title, notes=None, due=None)`
- `patch_task(tasklist_id, task_id, patch)` (complete, reschedule, edit)
- `delete_task(tasklist_id, task_id)`

`gtasks_seen` cache works identically. Signals: overdue >24h, no-due-date aged >7d, due date vs calendar conflict.

### 6.4 Autonomy policy

First-class `autonomy.py` module, not scattered if-statements. Exposes:

```python
policy.can_autoexecute(action: Action) -> Decision
# Decision = Allow | RequireReview(reason, draft_path)
```

**Auto-execute:**
- Any `wiki/` edit (as v0)
- Creating GCal events on the primary calendar with **no external attendees** (solo deep-work blocks, gym, prep, travel)
- Moving/rescheduling/deleting GCal events the agent itself created (identified by provenance tag)
- Creating, completing, rescheduling GTasks on the default list
- Reading any Google or Whoop resource

**Draft-only (lands in `/inbox`):**
- Creating or modifying any GCal event with external attendees (anything that sends an outbound invite)
- Modifying or deleting a GCal event the agent did not create (human-scheduled meetings are sacred)
- Any outbound email, Slack message, GitHub PR creation (reserved; out of scope for v1)

**Provenance tag.** Every agent-created GCal event and GTask gets `\n\n—brain/<run_id>` appended to its description. The tick's diff logic uses this tag to know which objects are agent-authored when deciding whether a modification is auto-executable.

**Policy evaluation is spanned.** Every call to `policy.can_autoexecute` emits a span with decision + reason. You can query Grafana for "which draft-only decisions fired this week and why?" to tune the policy over time.

### 6.5 Local policy proxy

A tiny HTTP proxy runs inside the `brain-worker` container image on `127.0.0.1:8001` with endpoints `/gcal/*` and `/gtasks/*`. The agent calls these via `curl` from tool invocations. The proxy forwards to brain-core over the host network, which runs `policy.can_autoexecute()` before hitting Google.

**Agents cannot bypass the policy by construction** because the `brain-runs` docker network has no route to `*.googleapis.com`. The only reachable Google access path is the local proxy, which is always gated. The policy is enforced in one place, not by every agent remembering to check.

### 6.6 Tick wiring

`tick.py` calls `gcal._tick()` and `gtasks._tick()` every 15 min. Each:
1. Fetches current state via `list_events` / `list_tasks`
2. Diffs against `gcal_seen` / `gtasks_seen` cache tables
3. Emits nudges on interesting changes
4. Updates cache rows

---

## 7. Information Architecture + Control Panel

### 7.1 Route map

```
/                        Dashboard (today + live system state)
/ingest                  Raw intake — text, URL, file, voice (deferred)
/wiki/[...slug]          Vault browser — render + edit-in-chat
/runs                    Live + queue + history of agent runs
/runs/[run_id]           Single-run deep dive
/inbox                   Drafts + merge conflicts awaiting review
/thesis                  Four-axis leverage dashboard
/chat                    Main thread
/chat/[thread_id]        Topic thread
/bench                   Benchmark reports + week-over-week graphs
/settings                Index
/settings/integrations   Google / Whoop / Claude OAuth status + connect
/settings/autonomy       Policy matrix — what the agent can auto-execute
/settings/jobs           Cron schedule + enable/disable + prompt overrides
/settings/scheduler      Warm pool bounds, class quotas, rate-limit ceilings
/settings/observability  Links to Grafana Cloud dashboards
/settings/spot           Instance state, drain test, interruption history
```

12 route groups. Every one has a real page in v1. If it can't be controlled from here, it doesn't exist.

`/capture` redirects to `/ingest` (preserves muscle memory; kills the old term).

### 7.2 Three-pillar framing

The sidebar's top section is visually grouped into three bands reflecting the Karpathy LLM-wiki pattern (ingest → wiki → output):

```
INGEST
  Ingest

WIKI
  Wiki
  Thesis
  Inbox ●5

OUTPUT
  Runs ●2
  Chat ●1
  Bench

SYSTEM
  Settings
```

Section labels are tiny muted gray headers. This is a visual reframe, not a backend restructure — vault folders, DB schema, and API shape are unchanged.

### 7.3 Key new routes

**`/runs`** — the "output" pillar centerpiece. Three tabs:

1. **Live.** Grid of active runs. Each row: `run_id` (monospaced 12px), agent class, trigger source, elapsed time, current phase (`pending → admitted → placing → running → reconciling` as text with the active one in the accent color and the rest muted), live-updating last 3 stream-json events.
2. **Queue.** Pending runs sorted by priority with the reason each is waiting (`itpm bucket full`, `otpm bucket full`, `no idle container`). Scheduler internal state made visible.
3. **History.** Paginated table with filters on class/trigger/outcome/date.

**`/runs/[run_id]`** — single-run deep dive. Five collapsible sections:
- **Timeline** — OTEL span tree rendered as an indented text tree (`├─`/`└─`), monospaced, duration in a muted right column
- **Prompt** — final prompt sent to `claude -p`, with system/context/user split
- **Stream** — full stream-json scrollback as chat bubbles + tool call blocks
- **Vault diff** — git diff of what the run changed
- **Cost** — input/output tokens, prompt cache hit ratio, dollar cost

**`/bench`** — benchmark report viewer. Grid of report cards. Main landing: a single chart — **prompt cache hit ratio over time** — with commit annotations. The interview demo backdrop.

**`/settings/integrations`** — OAuth connect flows for Google, Whoop, Claude. Separate from NextAuth. Status + scope info + reconnect button.

**`/settings/autonomy`** — policy matrix. Table with action categories down the left, three columns (Auto-execute / Review in inbox / Never), per-row toggle. Writes to `/var/brain/config/policy.json`, `autonomy.py` reloads on change.

**`/settings/jobs`** — every cron job. Columns: name, schedule (editable cron expr), enabled toggle, last run, next run, "Run now", model override. Writes to `/var/brain/config/jobs.yaml`.

**`/settings/scheduler`** — warm pool bounds, class quotas, ITPM/OTPM/RPM ceilings. Read-only in week 1; write in week 3+.

**`/settings/spot`** — instance state (`running on Spot`, current bid, launch time), last interruption, interruptions in 30d, "Simulate drain" button, drain-health over time.

### 7.4 Live data via SSE

Pages that show live data don't poll. They open a persistent SSE stream to `/api/events` that fans out scheduler state changes, sampled span events, and tick signals. One connection per open tab, multiplexed over topics. ~200 lines of FastAPI + ~100 lines of client-side reconnect.

### 7.5 Responsive web

Existing `Shell.tsx` becomes mobile-first via Tailwind v4 responsive utilities:
- Sidebar collapses to a burger menu under `md:` breakpoint, overlays content when opened
- Top bar shrinks; quick-capture becomes a bottom sheet on mobile
- `/runs` live grid becomes a vertical list on narrow viewports
- `/runs/[run_id]` timeline stacks vertically
- `/chat` main panel gets `env(safe-area-inset-bottom)` for iOS Safari
- Viewport meta + touch-action hints

No PWA, no service worker, no manifest.

### 7.6 Visual language

**Palette.**
- `zinc-50` background
- `zinc-900` text
- `zinc-200` dividers
- One accent: a single teal or indigo. Used for active states, selected row, one-chart primary line. Never for cards or backgrounds.

**Typography.**
- Geist Sans (UI) + Geist Mono (IDs, timestamps, tokens, costs, code)
- Weight carries hierarchy: 500 section labels, 600 headers, 400 body
- No heading larger than ~18px except `/` dashboard greeting

**Layout.**
- Sidebar + main with 1px `zinc-200` divider. No shadows.
- Top bar 48px, no border-bottom (thin divider on scroll)
- Status footer 28px, monospaced

**Specific pages.**
- `/runs` Live tab: text-first list, not a card grid. One run per row.
- `/runs/[run_id]` Timeline: indented text tree, monospaced, durations in right column. No flame graph in v1 (Grafana Cloud provides one).
- `/bench`: single line chart in accent color, 1px line, muted grid, no fill, no shadow.
- `/inbox`: list, not cards.
- `/settings/*`: form-style. Labels left, controls right, generous vertical spacing, section dividers, not cards. Reads like native Mac preferences.

**Forbidden.**
- No emoji in UI chrome
- No gradient backgrounds or cards
- No glow/shiny/neon effects
- Drop shadows no heavier than 1–2px
- No `rounded-2xl` bubble look (`rounded-md` max)
- No colorful badge clutter
- No sparkly language ("AI-powered", "smart")
- No five-accent rainbow palette

Reference anchors: Linear issues view, Vercel deployments page, Stripe dashboard payments table, Arc browser sidebar grouping.

---

## 8. Observability + Benchmark Harness

### 8.1 Why this is the centerpiece

Side projects read as hobby-grade without a number measured on the thing under realistic load. The north-star metric for brain-v1 is **prompt cache hit ratio**, and the story is: *"18% baseline → 73%+ after placement-aware scheduling, which drove P95 agent turn latency from ~4s to ~1.3s at 20 concurrent agents."*

Everything in this section exists to make that sentence defensible under scrutiny.

### 8.2 Stack

**Emitter side — brain-core:**

- `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-http` → OTLP HTTP to `127.0.0.1:4318` where `grafana-agent` receives and forwards to Grafana Cloud Tempo.
- `prometheus-client` exposing `/metrics` on `127.0.0.1:9100`. `grafana-agent` scrapes every 15s and `remote_write`s to Grafana Cloud Mimir.
- `structlog` JSON logs tailed by `grafana-agent` Loki exporter.

**Context propagation.** A FastAPI middleware attaches a `request_id` (ULID) to every incoming request, which becomes the root span attribute and propagates via `structlog.contextvars` to every log line. For any agent run, `run_id` + `request_id` unlocks the entire story across traces, metrics, and logs.

**Decorator-driven instrumentation.**

```python
@traced("scheduler.admission_pass")
@metered("scheduler.admission_runs")
async def run_admission_pass(self) -> AdmissionPassResult:
    ...
```

`@traced` creates a span with the function name, records exceptions, sets status. `@metered` records a duration histogram and a call counter tagged `success|failure`. No hand-written `with tracer.start_as_current_span(...)` blocks anywhere except for rare cases that need mid-execution span attributes.

### 8.3 Span catalog

Five trace trees, one per kind of system activity. Each has a stable root span carrying `run_id` as an attribute.

**Tree 1 — Agent run lifecycle** (root: `brain.run`, one trace per run):

```
brain.run
├─ scheduler.submit
├─ scheduler.admission_pass
├─ scheduler.dispatch
├─ sandbox.prepare_run
│  ├─ sandbox.worktree_create
│  └─ sandbox.container_start
├─ sandbox.exec
│  ├─ anthropic.request   (repeated; with cache attributes)
│  ├─ tool.call.<name>    (repeated)
│  └─ sandbox.exec_complete
├─ reconciler.reconcile
│  └─ reconciler.merge
└─ sandbox.reap_run
```

Each `anthropic.request` span records `{model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cache_hit_ratio, duration_ms}`. This is where the north-star metric comes from — measured at the point of truth, not inferred.

**Tree 2 — Tick cycle** (root: `brain.tick`, every 15 min):

```
brain.tick
├─ tick.whoop
├─ tick.gcal
└─ tick.gtasks
   └─ (HTTP calls, diff, nudge emissions as child spans)
```

**Tree 3 — Watcher cycle** (root: `brain.watcher`, bursty):

```
brain.watcher
├─ watcher.debounce
└─ watcher.emit_nudge
```

**Tree 4 — Ingest pipeline** (root: `brain.ingest`, per capture):

```
brain.ingest
├─ ingest.fetch
├─ ingest.classify
├─ ingest.file
└─ scheduler.submit   (for the summarize run that follows)
```

**Tree 5 — Benchmark run** (root: `bench.run`, explicit):

```
bench.run
├─ bench.loadgen
│  └─ (N parallel brain.run children)
├─ bench.collect
└─ bench.report
```

The benchmark trace is load-bearing for interview demos — a single flame graph showing 20 concurrent agents running through the system.

### 8.4 Metrics catalog

Every metric has a stable name, type, and labels. Cardinality is controlled: no user-id labels, no run-id labels.

**Scheduler:**
- `brain_admission_runs_total{class, outcome}` counter
- `brain_admission_queue_depth{class}` gauge
- `brain_admission_bucket_headroom_ratio{dimension}` gauge (0–1)
- `brain_admission_wait_seconds{class}` histogram
- `brain_placement_cache_affinity{outcome}` counter
- `brain_scheduler_tick_duration_seconds{loop}` histogram

**Sandbox:**
- `brain_sandbox_worktree_create_seconds{scope}` histogram
- `brain_sandbox_container_start_seconds` histogram
- `brain_sandbox_runs_concurrent` gauge
- `brain_sandbox_warm_pool_size{state}` gauge

**Anthropic API:**
- `brain_anthropic_requests_total{model, outcome}` counter
- `brain_anthropic_tokens_total{model, kind}` counter
- **`brain_anthropic_prompt_cache_hit_ratio{family}`** gauge — **north-star metric**
- `brain_anthropic_request_duration_seconds{model, outcome}` histogram

**Reconciler:**
- `brain_reconciler_merges_total{outcome}` counter
- `brain_reconciler_merge_duration_seconds{outcome}` histogram

**Run end-to-end:**
- `brain_run_duration_seconds{class, outcome}` histogram — the other key metric
- `brain_run_cost_dollars{class}` counter

### 8.5 Dashboards

Four Grafana Cloud dashboards, checked in as JSON at `infra/grafana/dashboards/` and deployed via the Grafana Cloud API (dashboard-as-code).

**1. `brain-v1 overview`** — 12 panels: runs/min, queue depth by class, admission rejections by reason, bucket headroom per dimension, **prompt cache hit ratio (big stat + timeseries)**, cache affinity by family, P50/P95/P99 run duration, warm pool occupancy, sandbox cold-start P95, reconciler outcome rate, tokens/min, estimated cost/hr.

**2. `brain-v1 prompt cache analysis`** — the interview demo backdrop. Drill-down for the north-star metric. Cache hit rate by family, P95 latency conditional on cache hit vs miss (two lines visually showing the optimization), tokens saved vs consumed, week-over-week trend.

**3. `brain-v1 scheduler trace`** — latency decomposition. Breakdown of agent run duration into its components (container start → prompt build → Anthropic round-trip → tool calls → reconcile → reap) from span durations.

**4. `brain-v1 Spot resilience`** — instance uptime, Spot interruption events (annotated), drain duration, time-to-recovery, runs interrupted vs successfully recovered.

### 8.6 Benchmark harness

Lives at `bench/`:

```
bench/
├── README.md
├── run.py                   entrypoint: python -m bench.run --profile P --concurrency N --duration D
├── loadgen/
│   ├── prompts.py           representative prompt fixtures per class
│   ├── generator.py         async generator spawning N synthetic submissions
│   └── profiles.py          ramp | sustained | burst | mixed
├── collect/
│   ├── grafana_query.py     pulls metrics + traces from Grafana Cloud via HTTP API
│   └── snapshot.py          dumps self-contained JSON of the run
├── report/
│   ├── template.md.j2       Jinja2 template
│   ├── charts.py            matplotlib: cache hit curve, latency CDF, queue depth
│   └── render.py            produces bench/reports/YYYY-MM-DD-HHMM.md + PNGs
└── reports/
    ├── 2026-04-20-baseline.md  week 1 baseline (no placement)
    ├── 2026-04-27-w2.md         after admission controller
    ├── 2026-05-04-w3.md         after cache-aware placement
    └── 2026-05-08-final.md      final numbers
```

**Load profiles.**
- `ramp`: 1 → N concurrent over 5 min, hold for 10 min
- `sustained`: N concurrent for 15 min
- `burst`: spike/drop/spike/drop — tests admission backpressure
- `mixed`: 60% chat, 20% synthesis, 15% ingest, 5% background

**Prompt fixtures are real prompts** from `jobs/` and representative chat turns, not synthetic strings. The load agents run `morning`, `arxiv-digest`, `thesis-review`, `lc-daily`, etc. against a test-mode git branch that's discarded at the end. Prompt-cache hit rate is only meaningful if prompts are production prompts.

**Report template** produces markdown with: summary (cache hit ratio, P95 duration, admission rejection rate, merge conflict rate, cost), cache hit ratio curve, latency CDF vs baseline, scheduler behavior panels, top 5 slowest runs with Grafana trace URLs, what changed since the last report (auto-generated from `git log`), known issues & follow-ups.

The last section feeds into the `self-write-blog` graduation job — each weekly report is a narrative chunk the system can assemble into the final blog post.

### 8.7 The interview story

*"I wanted to know whether my scheduler was actually helping, so I built a benchmark harness that runs real production prompts against the system at controllable concurrency, pulls metrics and traces back from Grafana Cloud, and produces a markdown report with a latency CDF, a cache-hit-rate curve, and the top slowest runs linked to their traces. I ran it weekly. Week 1 baseline: cache hit rate 18%, P95 run latency 4.1s at 20 concurrent. Week 4 final: 73% cache hit, 1.3s P95. The single biggest lever was realizing Anthropic's prompt cache is per-backend with a ~5-minute TTL, so random distribution across warm containers was losing almost all the cache value. Once I started pinning same-family runs to the same container for as long as the cache was warm, hit rate climbed almost 50 points and latency dropped 3x. Full report per week in the repo, here's the final comparison report, here's the Grafana dashboard, here's the trace of a representative run with the cache attributes in the Anthropic request span."*

---

## 9. Error Handling + Failure Modes

### 9.1 Failure taxonomy

| Category | Example | Recovery |
|---|---|---|
| Transient external | Anthropic 429, Google 503, GitHub SSH timeout | Exponential backoff in the call site, 5 attempts, 60s cap |
| Permanent external | Anthropic 400, Google invalid token | Fail the run, preserve response body, no retry |
| Run-internal | Agent exits non-zero, stream-json parse error | Mark `failed`, preserve worktree, file diagnostic |
| Git conflict | Reconciler three-way merge fails | Branch stays alive, inbox draft files, user adjudicates |
| Infrastructure | Disk full, OOM, FD exhaustion | Spot drain triggers even without AWS notice; systemd restart |
| Scheduler logic bug | Run stuck in `admitted` forever | Watchdog coroutine scans for `age > class_max + grace`, force-terminates, diagnoses |

### 9.2 Retry policy

- **Anthropic**: retry 429 and 5xx with exponential backoff (1s, 2s, 4s, 8s, 16s), respect `retry-after` header. **Never retry 400** (prompt bug wastes tokens).
- **Google**: same backoff, extend to 10 attempts on 401 (triggers a token refresh between), 5 on other errors. If refresh fails after 3, surface *"Google auth broken — reconnect at /settings/integrations/google"* and disable affected tick sub-loop.
- **Git**: no automatic retries. Failures are either transient-trivial (handled locally) or structural (need human).
- **SQLite writes**: no retry. A failed write means the disk is sick.

### 9.3 Poisoned runs

A run that fails repeatedly regardless of retry. Danger: cron re-enqueues every 15 min and burns tokens. Mitigation: every run carries `attempt_count`; on submission, check for recent same-`idempotency_key` runs in the last 24h with `state=failed`; if `count >= 3`, reject with `poisoned`, fire nudge, mark job `paused` in `/settings/jobs` until a human re-enables.

### 9.4 Partial-failure modes

- **Grafana Cloud unreachable** → `grafana-agent` buffers to local disk (500 MB, 72h retention). Nothing user-facing breaks. Ships when cloud returns.
- **Anthropic unreachable** → admission refuses new runs; UI banner *"Anthropic API unreachable"*; dashboard/wiki/inbox/runs history continue working; chat input disabled.
- **Google API unreachable** → tick sub-loops skip cycles; everything else runs. Nudge fires if >1h.
- **Secrets Manager unreachable** → in-memory tokens continue until expiry; at expiry, affected integration enters "unreachable" state.
- **brain-core crash** → systemd restart within 5s. On startup: reads `run_queue`; `state=running` with no live PID → re-enqueue with `attempt_count++` or mark failed if ≥3; `state=reconciling` → fresh reconciler pass against existing worktree. SSE reconnects automatically.
- **brain-web crash** → systemd restart, Caddy 502 briefly.

### 9.5 Spot drain

`spot/drain.py` runs as a systemd service polling `http://169.254.169.254/latest/meta-data/spot/instance-action` every 5s.

**T+0 (notice):**
1. Set `draining=True` via `/api/internal/drain` (localhost, no auth)
2. Scheduler refuses new submissions with 503
3. Emit span `spot.drain_started`
4. UI banner *"Instance is draining. Work in progress will complete; new runs queued."*

**T+0 to T+90s (graceful):**
- Running agents continue
- Every 5s check `running_count == 0`; if yes, short-circuit to shutdown
- Tick loops pause

**T+90s (force):**
1. SIGINT all running containers
2. Mark runs `interrupted` with `retry_after_recovery=True`
3. Flush reconciler
4. Fsync WAL + force checkpoint

**T+105s (shutdown prep):**
1. Stop brain-core
2. Stop brain-web
3. Stop grafana-agent (after local buffer flushes to EBS)
4. Emit span `spot.drain_complete`

**T+120s:** instance terminates.

**Recovery at boot of replacement instance** (runs as `spot/recovery.py` one-shot systemd service ordered before `brain-core`):

1. EBS volume mount (cloud-init)
2. `git -C /var/brain/vault.git fsck --no-progress`
3. Scan `run_worktrees` for orphans — resume reconciliation if branch exists, GC if worktree dir lost
4. Re-enqueue all `interrupted` runs at original priority
5. Start `grafana-agent` (ships buffered telemetry first)
6. Start `brain-core` (scheduler recovery re-reads queue)
7. Start `brain-web`
8. Nudge fires: *"Recovered from Spot interruption at {T}. N runs re-enqueued."*

**Drain simulation.** `/settings/spot` "Simulate drain" runs the full sequence except for the actual shutdown, reports time-to-drain, time-to-queue-recovery, and data-loss check. Safe to run weekly as a self-test.

### 9.6 Alerts → nudges

You are not on-call. All alerts route to in-app nudges. A loud (banner) nudge fires only for:

1. Cron job failed 3+ times in 24h (poisoned-run mechanic)
2. Google or Whoop auth broken >30 min
3. Spot interruption occurred (informational)
4. Benchmark regression: cache hit rate dropped >10pp, or P95 latency rose >30%
5. Disk usage >85%
6. Grafana Cloud ingest quota >90%

Each alert is a Prometheus rule in Grafana Cloud firing a webhook at `/api/internal/alert`, which writes a nudge row in SQLite. Appears in-app within 15s.

---

## 10. Testing Strategy

Calibrated to which pieces matter for correctness vs which are obvious in use. Target: "things that could silently break without showing in the dashboard get tested; obvious breakage doesn't."

### 10.1 Unit tests

**Get tests:**
- `scheduler/admission.py` — leaky bucket math, per-class quotas, EWMA estimator. ~25 cases including property-based tests via `hypothesis` for the invariant "total usage never exceeds ceiling."
- `scheduler/placement.py` — cache affinity scoring, tie-breaking, selection. ~15 cases.
- `reconciler/merge.py` + `reconciler/conflicts.py` — fast-forward succeeds, FF blocked → three-way succeeds, three-way blocked → conflict file generated. ~10 cases, temp git repo fixture.
- `integrations/google_oauth.py` — refresh dance, rotated-refresh-token edge case. Mock `requests`. ~8 cases.
- `autonomy.py` — policy matrix. ~15 cases, one per row.
- `spot/drain.py` — state machine transitions. Fake metadata endpoint. ~12 cases.

**Don't get tests:**
- `sandbox/container.py` (Docker wrapper — integration instead)
- `sandbox/exec.py` stream parsing (recorded stream fixture in integration)
- `ingest/fetchers.py` (thin lib wrappers)
- Route handlers in `main.py` (thin delegates — indirect via integration)
- `watcher.py` (slow + flaky to unit-test a filesystem observer)

Framework: `pytest` + `pytest-asyncio` + `hypothesis`. Target ~300–400 LoC of test code.

### 10.2 Integration tests

`tests/integration/` spins up real brain-core + real SQLite in `/tmp` + real local Docker + **fake Anthropic server** (`tests/fixtures/fake_anthropic.py`, ~100 LoC FastAPI app returning stream-json with configurable cache hit behavior). Fakes for Google and Whoop in the same shape.

**Scenarios:**
- End-to-end agent run: submit → worktree → container → fake Anthropic → reconcile → done. Assert queue transitions, worktree cleanup, metrics incremented.
- Merge conflict: two concurrent runs on the same file; one merges, other lands in inbox.
- Poisoned run: fake Anthropic errors 3 times; job goes `paused`.
- Spot drain simulation: trigger drain, verify no runs lost.

~10 tests, 50–150 LoC each, ~2 min total runtime.

### 10.3 Smoke tests

One Python script at `tests/smoke/smoke.py` that POSTs a known prompt to `/api/chat` against the live EC2, waits for SSE completion, verifies DB and git commit. ~30s runtime. Manual or GitHub Actions.

### 10.4 Benchmark-as-regression-test

Weekly CI job runs a 3-minute `bench/run.py` and compares cache hit rate + P95 latency to the most recent baseline. Cache hit drop >10pp or P95 rise >30% → job fails, fires regression nudge. Catches optimizations that undo prior optimizations.

### 10.5 CI

Single workflow `.github/workflows/ci.yml`:
- **PR:** `pytest tests/unit/` + `ruff check` + `mypy brain_core/` + `pnpm lint` + `pnpm typecheck`. Blocking.
- **Push to main:** integration tests + smoke test against prod. Non-blocking for hotfixes, warns.
- **Weekly scheduled:** bench regression check. Fires nudge on regression.
- **No deploy step.** Deploy is v0's push-to-main + the live `com.yogesh.brain.sync` 2-min git pull + systemd reload.

### 10.6 Explicitly not tested

- UI component tests for brain-web (change too often, low-value; manual iPhone Safari testing instead).
- OTEL span emission (you'd notice in Grafana Cloud).
- Prometheus metric registration (same).
- `ingest/fetchers.py` internet behavior (thin wrappers).

### 10.7 TDD discipline

TDD is not the default. Rule: **tests for last week's modules exist before this week's dependent work begins.** Moves fast in week 1; full coverage of critical paths by week 4.

---

## 11. Phasing

Four weeks, 7 days each, ~20–25 hours/week on top of existing LC and class load. Week 4 has deliberate slack so the blog-post finale doesn't crunch. Anchor: **writing-plans invoked 2026-04-14**, **month ends 2026-05-11**.

### 11.1 Week 1 — Foundations (2026-04-14 → 2026-04-20)

**Goal:** New EC2 instance up, scheduler stub accepting submissions, sandbox running a real agent in a real worktree, reconciler fast-forwarding the result, one job end-to-end through the new path.

**Days 1–2 (Mon–Tue) — Infra cutover.** Provision t4g.large Spot via Terraform, ASG(desired=1), migrate EBS volume, convert vault to bare repo + `worktrees/main/`, install `grafana-agent`, Grafana Cloud account, ingest heartbeat. Write **ADR 0003** (Grafana Cloud) and **ADR 0005** (t4g.large Spot).

**Days 3–4 (Wed–Thu) — Scheduler skeleton.** `scheduler/` module structure, `scheduler.submit()` writing to new `run_queue` table, admission + dispatch loops as no-op coroutines. New SQLite migration. Write **ADR 0002** (SQLite queue over Redis).

**Days 5–6 (Fri–Sat) — Sandbox skeleton + first real run.** `sandbox/worktree.py`, `sandbox/container.py`, pre-baked `brain-worker:v1` image (ARM64, Python + claude CLI + anthropic SDK), push to ECR private. `sandbox/exec.py` lifted from v0 agent.py, adapted for containerized streams. Wire through to first end-to-end run. Write **ADR 0001** (git-worktree sandbox, long-form).

**Day 7 (Sun) — Reconciler + documentation.** `reconciler/` fast-forward path working; three-way + conflict paths stubbed with TODO. Write `docs/architecture/modules.md` (initial) and `docs/architecture/README.md` (developer onboarding). **Week 1 benchmark:** `bench/run.py --profile sustained --concurrency 5 --duration 5m` with stubbed admission + placement. Report as `bench/reports/2026-04-20-baseline.md`. Tag `v1.0-foundations`.

**Delivers:** One agent run completes end-to-end through new path. Baseline benchmark exists. No intelligence in scheduler yet.

### 11.2 Week 2 — Intelligence + integrations (2026-04-21 → 2026-04-27)

**Goal:** Scheduler actually schedules, Google Tasks and Calendar real, autonomy policy enforced via local proxy.

**Days 1–2 (Mon–Tue) — Admission controller.** `scheduler/admission.py` per §4.2. Unit tests + hypothesis property tests. Wire into admission loop replacing no-op. All admission metrics + spans per §8. Verify in Grafana Cloud. Write **ADR 0004** (admission controller).

**Day 3 (Wed) — Placement.** `scheduler/placement.py` per §4.3. Wire into dispatch loop. Write **ADR 0004b** (cache-aware placement) — kept separate from 0004 so the two decisions can be read independently.

**Days 4–5 (Thu–Fri) — Google integrations.** `integrations/google_oauth.py`, `integrations/gcal.py`, `integrations/gtasks.py` per §6. `/api/oauth/google/{start,callback}` endpoints. `/settings/integrations/google` UI. OAuth through full consent flow once. Wire `tick.py` to call `gcal._tick()` + `gtasks._tick()`. Write **ADR 0006** (autonomy split).

**Day 6 (Sat) — Local policy proxy + autonomy.** `autonomy.py` module. HTTP proxy in `brain-worker` image exposing `/gcal/*` + `/gtasks/*`, forwarding to brain-core with policy gate. Configure `brain-runs` docker network egress allowlist. `/settings/autonomy` UI (read-only in week 2).

**Day 7 (Sun) — Week 2 benchmark + docs.** `bench/run.py --profile mixed --concurrency 10 --duration 10m`. Report as `bench/reports/2026-04-27-w2.md`. Expected cache hit: ~40–50% (first real delta from baseline). Update `modules.md`. Tag `v1.1-scheduling`.

**Delivers:** Real admission, real placement, Google Tasks + Calendar real, autonomy enforced by construction. First measured cache hit improvement.

### 11.3 Week 3 — Control panel + observability depth (2026-04-28 → 2026-05-04)

**Goal:** Full control panel, every route usable, complete observability story, benchmark harness final shape.

**Days 1–3 (Mon–Wed) — Control panel.** Build `/runs` (live/queue/history tabs), `/runs/[run_id]` deep dive, `/bench` report viewer, `/settings/jobs` (editable cron + toggle), `/settings/scheduler` (read + limited write), `/settings/spot` (state + simulate drain + history). Retrofit visual language across existing pages. `/settings/autonomy` becomes writable.

**Day 4 (Thu) — Responsive sweep.** Mobile-first breakpoints across shell. iPhone Safari testing. Bottom-sheet quick-capture, burger sidebar, safe-area insets.

**Days 5–6 (Fri–Sat) — Observability depth + bench harness final.** Four Grafana Cloud dashboards as JSON in `infra/grafana/dashboards/`, pushed via Grafana Cloud API on deploy (dashboard-as-code). Finalize benchmark harness: load profiles, fake Anthropic server for CI, report template, matplotlib charts. `bench/collect/grafana_query.py` pulls metrics from Mimir HTTP API + traces from Tempo. Wire weekly regression CI job.

**Day 7 (Sun) — Week 3 benchmark + Spot drain test.** `bench/run.py --profile sustained --concurrency 20 --duration 15m` — full target concurrency. Report as `bench/reports/2026-05-04-w3.md`. Expected: 65–75% cache hit, 1.3–1.8s P95. Close to final interview number. Run `/settings/spot` "Simulate drain" once, capture timing, write **ADR 0007** (Spot drain characterization). Tag `v1.2-panel`.

**Delivers:** Complete control panel, full observability, near-final benchmark numbers. Interview demo is now possible.

### 11.4 Week 4 — Polish, self-authoring blog post, ship (2026-05-05 → 2026-05-11)

**Goal:** Bugs fixed, edges closed, system writes its own blog post, public URL ready, design doc becomes final artifact.

**Days 1–2 (Mon–Tue) — Bug bash.** Fix what real use has exposed. Harden reconciler three-way path. Verify poisoned-run mechanic by triggering it. Verify Grafana Cloud buffer-on-disconnect. **Delete `run-job.sh --direct` fallback** — scheduler has proven itself.

**Day 3 (Wed) — `self-write-blog` job.** New job at `jobs/self-write-blog.md` runs a Sonnet 4.6 agent with access to: `docs/architecture/decisions/`, latest bench reports, `git log` since project start, `wiki/log.md`, `docs/design/brain-v1.md`. Prompt: *"Write a technical blog post about how this system was built, why, the numbers, what didn't work, what you'd do differently. 2000–3000 words. Clinical voice, concrete numbers, one anecdote per section. Output to `output/blog-post-draft.md`."* Run, edit, iterate until publishable. The system demonstrates it works by documenting itself.

**Day 4 (Thu) — Final benchmark + comparison.** `bench/run.py --profile mixed --concurrency 20 --duration 30m`. Longest run of the project. Report as `bench/reports/2026-05-08-final.md`. Write `bench/reports/final-comparison.md` putting all four benchmarks side by side — cache hit curve, P95 latency, tokens per run. The single artifact handed to interviewers.

**Day 5 (Fri) — Design doc as final artifact.** Update `docs/design/brain-v1.md` with an epilogue section *"What actually shipped vs what was designed"*. Update `modules.md` for final layout. Write `docs/README.md` as top-level entry point.

**Day 6 (Sat) — Public URL + demo prep.** Build public read-only mode at `/public/*` — bench reports + selected anonymized runs, no OAuth gate. Shareable with recruiters. Record 3-minute screen walkthrough: dashboard → runs → deep dive → bench report → cache hit curve.

**Day 7 (Sun) — Final tag + blog post publish + retro.** Publish the blog post (personal site or GitHub Pages). URL goes into `docs/design/brain-v1.md`. Tag `v1.3-final`. Write **ADR 0099** (retrospective — what worked, didn't, would change).

**Delivers:** Final benchmark numbers, publishable system-authored blog post, public URL, finished interview story.

### 11.5 Concrete artifact list

Everything below exists in the repo or on a public URL when the month ends:

1. `brain-yseenich.duckdns.org` — live control panel on ~$15/month Spot
2. `docs/design/brain-v1.md` — design doc with epilogue
3. `docs/architecture/decisions/0001..NNNN.md` — every material decision documented
4. `docs/architecture/modules.md` — living module map
5. `bench/reports/*.md` — four weekly reports + final comparison
6. Four Grafana Cloud dashboards (JSON in `infra/grafana/dashboards/`)
7. `output/blog-post.md` — system-authored technical blog post, published
8. 3-minute screen recording demo
9. Git log as cohesive narrative with weekly tags (`v1.0-foundations` → `v1.3-final`)
10. The interview paragraph: *"cache hit 18% → 73%, P95 latency 4.1s → 1.3s at 20 concurrent, $15/month on Spot, here's the dashboard."*

---

## 12. Appendix: ADRs to Write

Planned ADRs to land during the build. Numbers reserved; content lands when the work happens.

| # | Slug | Week |
|---|---|---|
| 0001 | git-worktree-sandbox | 1 |
| 0002 | sqlite-queue-over-redis | 1 |
| 0003 | grafana-cloud-vs-local | 1 |
| 0004 | admission-controller-design | 2 |
| 0004b | cache-aware-placement | 2 |
| 0005 | t4g-large-spot | 1 |
| 0006 | autonomy-policy-split | 2 |
| 0007 | spot-drain-characterization | 3 |
| 0008 | benchmark-harness-shape | 3 |
| 0099 | retrospective | 4 |

New decisions made mid-build that aren't on this list land as numbered ADRs too, in the order they happen.

---

## 13. Open Questions (to resolve during writing-plans)

- Exact base image for `brain-worker:v1` — `python:3.12-slim-bookworm` (Debian-based, familiar) or `python:3.12-alpine` (smaller, musl quirks). Default: slim-bookworm unless image size becomes a cold-start issue.
- Whether to route `grafana-agent` OTLP ingress via a unix socket or a localhost TCP port. Default: TCP `127.0.0.1:4318` because it matches the OTEL SDK's default and debugging with curl is easier.
- How to handle the OAuth state parameter for the Google OAuth flow — CSRF-style token in a secure cookie, or a server-side short-TTL store. Default: secure cookie, lighter.
- Whether the `self-write-blog` job should run in-sandbox like every other job, or exceptionally bypass the sandbox to get read access to `docs/architecture/decisions/` without configuring a read-only bind. Default: run in-sandbox with a read-only bind-mount of `docs/` added to the job spec.

These are resolved during writing-plans, not during brainstorming.

---

**End of design.**
