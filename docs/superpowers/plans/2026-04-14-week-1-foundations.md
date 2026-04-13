# brain-v1 · Week 1 — Foundations · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the new EC2 t4g.large Spot instance, convert the vault to a bare git repo with per-run worktrees, scaffold the `scheduler/`, `sandbox/`, and `reconciler/` modules inside `brain-core`, and run one agent end-to-end through the new path. Ship `v1.0-foundations` tag and a baseline benchmark report.

**Architecture:** A single-node `brain-core` FastAPI process owns a `scheduler` (three async loops: ingress/admission/dispatch) that drains a SQLite `run_queue` table and spawns per-run Docker sandboxes against per-run git worktrees carved from `/var/brain/vault.git` (bare). A `reconciler` fast-forwards finished runs back to `main`. Observability is emitted via OpenTelemetry OTLP HTTP + Prometheus `/metrics` to a local `grafana-agent`, which ships to Grafana Cloud free tier. Week 1 admission and placement are deliberate stubs — the scaffolding exists, the intelligence lands in Week 2.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, pytest + pytest-asyncio + hypothesis, Docker (ARM64), git worktrees, AWS (EC2 Spot, ASG, EBS, ECR, Secrets Manager) via Terraform, grafana-agent → Grafana Cloud.

**Design doc:** [docs/design/brain-v1.md](../../design/brain-v1.md) · [docs/superpowers/specs/2026-04-13-brain-v1-design.md](../specs/2026-04-13-brain-v1-design.md)

**Timeline:** 2026-04-14 (Mon) → 2026-04-20 (Sun). Seven working days. Tag `v1.0-foundations` on Day 7.

**Delivers (definition of done for Week 1):**
1. `t4g.large` Spot instance running, EBS-persisted state, ASG(desired=1) in place
2. `/var/brain/vault.git` bare repo with `worktrees/main/` as the live reader
3. `grafana-agent` systemd service shipping metrics + traces + logs to Grafana Cloud; heartbeat visible in the Grafana Cloud UI
4. `brain_core.scheduler` package with `submit()`, no-op admission loop, no-op dispatch loop, new `run_queue` SQLite table, ≥90% unit test coverage for `submit()` and the state machine
5. `brain_core.sandbox` package with `worktree.prepare_run` / `worktree.reap_run`, `container.start_run` / `container.stop_run`, `exec.stream_run` (stream-json parser lifted from v0 `agent.py`)
6. `brain-worker:v1` ARM64 Docker image pushed to ECR private
7. `brain_core.reconciler` package with fast-forward merge path (three-way and conflict stubbed with explicit `NotImplementedError`)
8. One real agent run submitted via `scheduler.submit()`, executed in a worktree sandbox, reconciled fast-forward back to `main` — verified end-to-end
9. `bench/` scaffold, `bench/reports/2026-04-20-baseline.md` with a 5-concurrent / 5-minute sustained profile run
10. ADR 0001 (git-worktree sandbox), ADR 0002 (SQLite queue over Redis), ADR 0003 (Grafana Cloud vs local), ADR 0005 (t4g.large Spot) committed
11. `docs/architecture/README.md`, `docs/architecture/modules.md` scaffolded
12. `v1.0-foundations` git tag

## File Structure

### New files this week
```
apps/brain-core/brain_core/
├── scheduler/
│   ├── __init__.py
│   ├── types.py           # Run, RunState, Priority, AgentClass, AdmissionDecision
│   ├── queue.py           # run_queue SQLite row helpers (aiosqlite)
│   ├── submit.py          # scheduler.submit() public entry point
│   ├── admission.py       # admission loop (no-op in W1)
│   ├── dispatch.py        # dispatch loop (no-op → wired to sandbox on Day 6)
│   └── runner.py          # start_scheduler() — launches the three loops
├── sandbox/
│   ├── __init__.py
│   ├── types.py           # WorktreeHandle, ContainerHandle, RunOutcome
│   ├── worktree.py        # prepare_run / reap_run (git worktree add/remove)
│   ├── container.py       # start_run / stop_run (docker run wrapper)
│   ├── exec.py            # stream-json parser + SSE fan-out glue
│   └── lifecycle.py       # glue: prepare → start → stream → reap
├── reconciler/
│   ├── __init__.py
│   ├── types.py           # ReconcileOutcome (merged, conflicted, failed)
│   └── merge.py           # fast-forward path; three-way/conflict raise NotImplementedError
├── observability/
│   ├── __init__.py
│   ├── tracing.py         # OTLP HTTP exporter setup; @traced decorator
│   ├── metrics.py         # prometheus_client registry; @metered decorator
│   └── logs.py            # structlog JSON configuration
└── migrations/
    └── 0002_run_queue.sql # CREATE TABLE run_queue (...)

apps/brain-core/tests/
├── __init__.py
├── conftest.py            # shared fixtures: temp git repo, temp sqlite, fake clock
├── unit/
│   ├── test_scheduler_queue.py
│   ├── test_scheduler_submit.py
│   ├── test_scheduler_state_machine.py
│   ├── test_sandbox_worktree.py
│   └── test_reconciler_merge.py
└── integration/
    └── test_end_to_end_run.py

infra/
├── terraform/
│   ├── spot.tf             # new: t4g.large ASG + launch template + spot config
│   ├── ebs.tf              # new: standalone gp3 EBS volume for /var/brain
│   └── ecr.tf              # new: private ECR repo for brain-worker
├── ec2/
│   ├── cloud-init-v1.yaml  # replaces bootstrap.md manual steps
│   └── systemd/
│       ├── brain-core.service       # modify: point BRAIN_DB_PATH at /var/brain
│       ├── grafana-agent.service    # new
│       └── spot-recovery.service    # new one-shot service (stub in W1)
└── docker/
    └── brain-worker/
        ├── Dockerfile        # ARM64; python:3.12-slim-bookworm + claude CLI + anthropic SDK
        ├── run-agent.sh      # container entrypoint: exec claude -p with args
        └── build-and-push.sh # one-shot ECR push helper

docs/architecture/
├── README.md              # developer onboarding entry point
├── modules.md             # living module map
└── decisions/
    ├── 0001-git-worktree-sandbox.md
    ├── 0002-sqlite-queue-over-redis.md
    ├── 0003-grafana-cloud-vs-local.md
    └── 0005-t4g-large-spot.md

bench/
├── README.md
├── run.py                 # `python -m bench.run --profile P --concurrency N --duration D`
├── loadgen/
│   ├── __init__.py
│   ├── profiles.py        # ramp | sustained | burst | mixed
│   └── generator.py       # async generator spawning N synthetic submissions
├── report/
│   ├── __init__.py
│   ├── template.md.j2     # Jinja2 template
│   └── render.py          # reads queue metrics + writes report
└── reports/
    └── 2026-04-20-baseline.md   # generated Day 7
```

### Existing files modified this week
- `apps/brain-core/pyproject.toml` — add dev deps: pytest, pytest-asyncio, hypothesis, structlog, opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http, prometheus-client, jinja2, matplotlib
- `apps/brain-core/brain_core/main.py` — wire `start_scheduler()` on FastAPI startup; add `/api/internal/drain` stub
- `apps/brain-core/brain_core/db.py` — add `DB_PATH` indirection that respects `/var/brain/db/brain.sqlite` on EC2; add migration runner
- `infra/terraform/main.tf` — reference new `spot.tf`, `ebs.tf`, `ecr.tf`; retire old on-demand instance resource (keep as commented safety net through Day 6, delete Day 7)
- `.scripts/run-job.sh` — add `--direct` fallback flag (safety valve, deleted in Week 4)

---

## Phases

- **Phase A** — Documentation scaffolding (Day 1 morning)
- **Phase B** — Infra: ECR + ASG + Spot launch template + EBS (Day 1 afternoon → Day 2)
- **Phase C** — Vault → bare repo conversion (Day 2 afternoon)
- **Phase D** — Grafana Cloud + grafana-agent heartbeat (Day 2 evening)
- **Phase E** — SQLite migration + run_queue + pytest setup (Day 3)
- **Phase F** — scheduler/ package (Day 3 → Day 4)
- **Phase G** — sandbox/worktree (Day 5 morning)
- **Phase H** — brain-worker Docker image + ECR push (Day 5 afternoon)
- **Phase I** — sandbox/container + sandbox/exec (Day 5 evening → Day 6)
- **Phase J** — End-to-end wiring (Day 6 afternoon)
- **Phase K** — reconciler/ fast-forward (Day 7 morning)
- **Phase L** — bench/ scaffold + baseline report + tag (Day 7 afternoon)

---

## Phase A — Documentation scaffolding

### Task A1: Create `docs/architecture/` and first ADRs

**Files:**
- Create: `docs/architecture/README.md`
- Create: `docs/architecture/modules.md`
- Create: `docs/architecture/decisions/README.md`
- Create: `docs/architecture/decisions/0001-git-worktree-sandbox.md`
- Create: `docs/architecture/decisions/0002-sqlite-queue-over-redis.md`
- Create: `docs/architecture/decisions/0003-grafana-cloud-vs-local.md`
- Create: `docs/architecture/decisions/0005-t4g-large-spot.md`

- [ ] **Step 1: Write `docs/architecture/README.md`**

```markdown
# Architecture — brain-v1

Entry point for developers onboarding to the brain-v1 codebase.

**Start here, then read in this order:**

1. [../design/brain-v1.md](../design/brain-v1.md) — the canonical design doc (spec)
2. [modules.md](modules.md) — living module map: what lives where and why
3. [decisions/](decisions/) — every material technical choice, one ADR per decision

## Top-level layout

```
apps/brain-core/     FastAPI orchestrator (Python 3.12)
apps/brain-web/      Next.js 16 + Tailwind v4 control panel
bench/               benchmark harness + weekly reports
docs/architecture/   this directory — the map
docs/design/         design docs (mirror of docs/superpowers/specs/)
infra/terraform/     AWS resources
infra/ec2/           cloud-init + systemd units + cron
infra/docker/        container images
jobs/                job prompts (markdown)
wiki/                LLM-maintained knowledge base
raw/                 immutable ingested sources
```

## How to add a feature

1. Read the design doc section covering the area
2. Read the relevant ADR(s) in `decisions/`
3. Find the module in `modules.md`; open its file
4. If the change introduces a new material decision, write a new dated ADR
5. Update `modules.md` if boundaries changed
```

- [ ] **Step 2: Write `docs/architecture/modules.md` scaffold**

```markdown
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
```

- [ ] **Step 3: Write `docs/architecture/decisions/README.md`**

```markdown
# Architecture Decision Records

Numbered, dated, durable. One ADR per material choice.

## Format

Every ADR uses this template:

```
# NNNN — <slug>

**Status:** Proposed | Accepted | Superseded-by-NNNN
**Date:** YYYY-MM-DD
**Deciders:** <who>

## Context
<what forced the decision>

## Decision
<what we chose, in one paragraph>

## Alternatives considered
- <option>: <why not>

## Consequences
### Positive
- ...
### Negative
- ...
### Neutral
- ...
```

## What gets an ADR

- Algorithm switches, new dependencies, data-flow changes, trust-boundary changes, runtime choices, cost tradeoffs, retry/timeout policies, protocol choices

## What does not

- Bug fixes, refactors, renames, test additions, dependency version bumps, typo fixes — these go in commit messages
```

- [ ] **Step 4: Write ADR 0001 (git-worktree sandbox)**

```markdown
# 0001 — git-worktree sandbox

**Status:** Accepted
**Date:** 2026-04-14
**Deciders:** Yogesh Seenichamy

## Context
brain v0 runs agents bare-metal as `claude -p` subprocesses against the live vault. This works for one agent. It breaks down immediately with concurrent agents: writes race, reads see partial state, nothing is isolated from anything else. The design calls for 10–20 concurrent agents on one node.

## Decision
Every agent run executes inside a short-lived git worktree carved from a bare `/var/brain/vault.git` repo. The live reader (brain-core routes, watcher) reads from `/var/brain/worktrees/main/`, which is itself just a long-lived worktree on branch `main`. Per-run worktrees live at `/var/brain/worktrees/run-<uuid>/` on branch `agent/run-<uuid>`. When a run finishes, a reconciler fast-forwards (or three-way merges) the run's branch back into `main` and deletes the worktree.

## Alternatives considered
- **Shared bind mount with file locks.** Rejected: locks don't compose with agent edits, and conflicts become silent.
- **Separate full clones per run.** Rejected: cost of cloning grows with vault size; worktrees share the object store.
- **Copy-on-write via overlayfs.** Rejected: Linux-specific, brittle across kernels, hard to reason about, no natural merge story.
- **Firecracker microVMs.** Rejected: too expensive for t4g.large; wrong instance family.

## Consequences
### Positive
- Natural isolation primitive — git already models parallel work
- Conflicts become first-class: the reconciler can three-way merge or file a conflict draft
- Sparse-checkout supports scoped runs (~80ms for scoped, ~400ms for full)
- Shared object store keeps disk cost bounded
### Negative
- `git gc` must be disabled on the bare repo to keep unresolved branches alive
- Worktree creation is on the critical path for run latency (mitigated by sparse-checkout)
- Adds operational complexity to backup/restore (one directory, multiple worktrees)
### Neutral
- Every agent run has a durable branch name — tracing, audit, and rollback all become easy
```

- [ ] **Step 5: Write ADR 0002 (SQLite queue over Redis)**

```markdown
# 0002 — SQLite queue over Redis

**Status:** Accepted
**Date:** 2026-04-14
**Deciders:** Yogesh Seenichamy

## Context
The scheduler needs a durable job queue. Enqueue rate peaks at ~50/min (cron + tick + chat + watcher). The instance is single-node. brain-core already runs an aiosqlite connection in WAL mode with thousands of writes/min without contention.

## Decision
Use a `run_queue` table in the existing SQLite database as the durable queue. No Redis, no RabbitMQ, no SQS. The scheduler polls with 50ms admission and 20ms dispatch loops — well below any rate we care about.

## Alternatives considered
- **Redis Streams.** Rejected: adds a daemon, ~100MB RAM, another failure mode, and brings nothing at this load.
- **SQS.** Rejected: cross-network latency defeats sub-100ms dispatch; extra cost; single-node project.
- **In-memory `asyncio.Queue`.** Rejected: loses work on crash or Spot drain; no introspection for `/runs` queue view.

## Consequences
### Positive
- One durable store; backup is one file
- Debuggable with `sqlite3` CLI / `python3 -c "import sqlite3"`
- `/runs` queue view is a simple `SELECT`
- Survives Spot drain via WAL checkpoint + fsync in the drain sequence
### Negative
- Polling, not push — a 50ms loop is fine, but load-bearing if we ever want lower latency
- Single-writer semantics on the queue table (acceptable; admission is single-threaded anyway)
### Neutral
- Interview story: "polling a well-indexed SQLite table beats a Redis dependency at this scale — prove it with the benchmark"
```

- [ ] **Step 6: Write ADR 0003 (Grafana Cloud vs local)**

```markdown
# 0003 — Grafana Cloud free tier vs local Prometheus/Tempo/Grafana

**Status:** Accepted
**Date:** 2026-04-14
**Deciders:** Yogesh Seenichamy

## Context
The design makes observability the interview centerpiece (OTEL traces + Prom metrics + structlog logs). Running Prometheus + Tempo + Grafana locally costs ~1.5 GB RAM and operational care. Target instance is t4g.large (8 GB RAM), Spot, $15/month.

## Decision
Use Grafana Cloud free tier. A local `grafana-agent` systemd service receives OTLP HTTP on `127.0.0.1:4318`, scrapes `brain-core:/metrics`, tails structlog JSON, and `remote_write`s to Grafana Cloud Mimir / Tempo / Loki. Dashboards live as JSON in `infra/grafana/dashboards/` and are pushed via the Grafana Cloud API.

## Alternatives considered
- **Local Prometheus + Tempo + Grafana.** Rejected: RAM budget, ops burden.
- **Datadog / Honeycomb.** Rejected: cost, vendor lock-in at larger scale.
- **Self-host Grafana, use free-tier Mimir/Tempo.** Rejected: no gain — Grafana Cloud's free tier includes Grafana itself.

## Consequences
### Positive
- Zero local RAM for the observability stack except `grafana-agent` (~60 MB)
- Dashboards survive instance replacement without backup
- Free-tier ingest (10k metrics, 50 GB logs, 50 GB traces/month) is ~5x our peak
### Negative
- Network egress required for telemetry (mitigated: `grafana-agent` buffers locally on disconnect)
- Free tier terms may change (mitigated: dashboard-as-code is portable to any Grafana instance)
### Neutral
- `grafana-agent` version is pinned in cloud-init; upgrades are a deliberate step
```

- [ ] **Step 7: Write ADR 0005 (t4g.large Spot)**

```markdown
# 0005 — t4g.large ARM64 on AWS Spot

**Status:** Accepted
**Date:** 2026-04-14
**Deciders:** Yogesh Seenichamy

## Context
v0 runs on `t4g.small` on-demand. v1 adds a scheduler, warm-pool of Docker containers, observability stack, and 10–20 concurrent agents. Memory pressure is the binding constraint: each containerized `claude -p` holds ~300 MB resident, and grafana-agent needs headroom. Cost target is ~$15/month.

## Decision
Upgrade to `t4g.large` (2 vCPU, 8 GB RAM, ARM64). Launch as Spot via an ASG with `desired_capacity=1`. On interruption, the ASG replaces the instance; EBS state persists; `spot/recovery.py` one-shot systemd service re-enqueues `interrupted` runs at boot.

## Alternatives considered
- **t4g.large on-demand.** Rejected: ~$30/month, no interruption story to tell.
- **t4g.medium Spot.** Rejected: 4 GB RAM is too tight for 10 concurrent agents + grafana-agent + brain-web + Caddy.
- **m7g.large Spot.** Rejected: more CPU than we need; cost is ~2x.
- **x86 t3.medium.** Rejected: ARM is ~20% cheaper and our stack is all Python + Docker, fully portable.

## Consequences
### Positive
- ~$14/month at current Spot prices in us-west-2 (verified 2026-04-13)
- Spot interruption handling becomes an interview story (the drain sequence)
- 8 GB RAM fits 20 concurrent agents with headroom
### Negative
- Spot interruption is a real event that must be tested (W1 stubs recovery; W3 simulates drain)
- ARM64 requires ARM64 Docker images (`brain-worker:v1` built for `linux/arm64`)
### Neutral
- Terraform module is reusable for other projects
```

- [ ] **Step 8: Commit documentation scaffolding**

```bash
git add docs/architecture/
git commit -m "docs(brain-v1): add architecture README, module map, ADRs 0001/0002/0003/0005"
```

Expected: commit succeeds; `git log -1 --stat` shows 7 new files under `docs/architecture/`.

---

## Phase B — Infra: ECR + ASG + Spot launch template + EBS

### Task B1: Create private ECR repo for brain-worker image

**Files:**
- Create: `infra/terraform/ecr.tf`
- Modify: `infra/terraform/outputs.tf` — add `brain_worker_ecr_url` output

- [ ] **Step 1: Write `infra/terraform/ecr.tf`**

```hcl
resource "aws_ecr_repository" "brain_worker" {
  name                 = "brain/brain-worker"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "brain_worker_retain_10" {
  repository = aws_ecr_repository.brain_worker.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
```

- [ ] **Step 2: Add ECR URL to outputs**

Append to `infra/terraform/outputs.tf`:

```hcl
output "brain_worker_ecr_url" {
  description = "ECR repo URL for pushing brain-worker:vN"
  value       = aws_ecr_repository.brain_worker.repository_url
}
```

- [ ] **Step 3: Plan and apply**

```bash
cd infra/terraform
AWS_PROFILE=brain terraform plan -out=ecr.tfplan
AWS_PROFILE=brain terraform apply ecr.tfplan
AWS_PROFILE=brain terraform output brain_worker_ecr_url
```

Expected: `aws_ecr_repository.brain_worker: Creation complete`; output prints a URL like `<acct>.dkr.ecr.us-west-2.amazonaws.com/brain/brain-worker`. Save that URL — Phase H needs it.

- [ ] **Step 4: Commit**

```bash
git add infra/terraform/ecr.tf infra/terraform/outputs.tf
git commit -m "infra(brain-v1): add private ECR for brain-worker image"
```

### Task B2: Create standalone EBS volume for `/var/brain`

**Files:**
- Create: `infra/terraform/ebs.tf`
- Modify: `infra/terraform/outputs.tf` — add `brain_state_volume_id` output

**Why standalone:** the volume must survive instance replacement on Spot interruption. It is attached by the launch template on boot, not by the instance resource.

- [ ] **Step 1: Write `infra/terraform/ebs.tf`**

```hcl
resource "aws_ebs_volume" "brain_state" {
  availability_zone = data.aws_subnets.default.ids[0] != "" ? element(data.aws_subnets.default.ids, 0) : null
  size              = 200
  type              = "gp3"
  iops              = 3000
  throughput        = 125
  encrypted         = true

  tags = {
    Name = "brain-state"
    Role = "persistent-state-v1"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# The AZ must match the ASG subnet. We derive it from the subnet's AZ attribute.
data "aws_subnet" "first_default" {
  id = element(data.aws_subnets.default.ids, 0)
}

# Replace the hardcoded AZ in the volume above. In practice:
#   terraform import aws_ebs_volume.brain_state <existing-vol-id>
# if migrating from an existing on-demand volume.
```

**Note to implementer:** the `availability_zone` line above is a placeholder expression — replace with `data.aws_subnet.first_default.availability_zone` after the `data` block is defined, then re-order so `data.aws_subnet.first_default` is above `aws_ebs_volume.brain_state`. The final form:

```hcl
data "aws_subnet" "first_default" {
  id = element(data.aws_subnets.default.ids, 0)
}

resource "aws_ebs_volume" "brain_state" {
  availability_zone = data.aws_subnet.first_default.availability_zone
  size              = 200
  type              = "gp3"
  iops              = 3000
  throughput        = 125
  encrypted         = true

  tags = {
    Name = "brain-state"
    Role = "persistent-state-v1"
  }

  lifecycle {
    prevent_destroy = true
  }
}
```

- [ ] **Step 2: Add volume id to outputs**

Append to `infra/terraform/outputs.tf`:

```hcl
output "brain_state_volume_id" {
  description = "EBS volume id for /var/brain (persistent across Spot interruptions)"
  value       = aws_ebs_volume.brain_state.id
}
```

- [ ] **Step 3: Plan and apply**

```bash
AWS_PROFILE=brain terraform plan -out=ebs.tfplan
AWS_PROFILE=brain terraform apply ebs.tfplan
AWS_PROFILE=brain terraform output brain_state_volume_id
```

Expected: one new `aws_ebs_volume.brain_state` created. Record the volume id.

- [ ] **Step 4: Commit**

```bash
git add infra/terraform/ebs.tf infra/terraform/outputs.tf
git commit -m "infra(brain-v1): provision standalone 200GB gp3 EBS for /var/brain"
```

### Task B3: Cloud-init user-data for the new instance

**Files:**
- Create: `infra/ec2/cloud-init-v1.yaml`

This is the unit of shell glue the launch template runs on first boot of every replacement instance. It must be idempotent — the same script runs on the first boot and every Spot replacement.

- [ ] **Step 1: Write `infra/ec2/cloud-init-v1.yaml`**

```yaml
#cloud-config
# brain-v1 cloud-init — runs on first boot + every Spot replacement.
# Idempotent: all steps safe to re-run.

package_update: true
package_upgrade: false

packages:
  - git
  - jq
  - python3-pip
  - python3-venv
  - docker.io
  - unzip
  - xfsprogs

write_files:
  - path: /etc/brain/version
    content: "v1.0-foundations"
    permissions: '0644'

  - path: /usr/local/bin/mount-brain-state.sh
    permissions: '0755'
    content: |
      #!/usr/bin/env bash
      set -euo pipefail
      # Find the attached brain-state volume (tagged Role=persistent-state-v1) by
      # the filesystem label we stamp on first boot.
      DEV=$(lsblk -ndo NAME,SIZE,TYPE | awk '$3=="disk" && $2=="200G" {print "/dev/"$1; exit}')
      if [ -z "$DEV" ]; then
        echo "brain-state volume not found" >&2; exit 1
      fi
      if ! blkid "$DEV" >/dev/null 2>&1; then
        mkfs.xfs -L brain-state "$DEV"
      fi
      mkdir -p /var/brain
      mountpoint -q /var/brain || mount "$DEV" /var/brain
      grep -q '/var/brain' /etc/fstab || echo "LABEL=brain-state /var/brain xfs defaults,nofail 0 2" >> /etc/fstab
      mkdir -p /var/brain/{vault.git,worktrees,db,scratch,config,logs}
      chown -R ubuntu:ubuntu /var/brain

runcmd:
  - [ systemctl, enable, --now, docker ]
  - [ usermod, -aG, docker, ubuntu ]
  - [ /usr/local/bin/mount-brain-state.sh ]
  # grafana-agent + brain-core systemd install happens in Phase D and via Ansible-lite shell in bootstrap; this cloud-init only brings up the host.
```

- [ ] **Step 2: Commit**

```bash
git add infra/ec2/cloud-init-v1.yaml
git commit -m "infra(brain-v1): cloud-init for t4g.large Spot host (mount EBS, docker, dirs)"
```

### Task B4: Launch template + ASG + Spot configuration

**Files:**
- Create: `infra/terraform/spot.tf`
- Modify: `infra/terraform/outputs.tf` — add `brain_asg_name`, `brain_launch_template_id`

- [ ] **Step 1: Write `infra/terraform/spot.tf`**

```hcl
resource "aws_iam_role" "brain_instance_v1" {
  name = "brain-instance-v1"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "brain_ssm_v1" {
  role       = aws_iam_role.brain_instance_v1.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "brain_runtime_v1" {
  name = "brain-runtime-v1"
  role = aws_iam_role.brain_instance_v1.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsRead"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
        Resource = [
          "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:brain/*",
        ]
      },
      {
        Sid    = "SecretsWriteClaude"
        Effect = "Allow"
        Action = ["secretsmanager:PutSecretValue"]
        Resource = [
          "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:brain/claude_credentials-*",
        ]
      },
      {
        Sid    = "EcrPull"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
        ]
        Resource = "*"
      },
      {
        Sid    = "AttachBrainVolume"
        Effect = "Allow"
        Action = ["ec2:AttachVolume", "ec2:DetachVolume", "ec2:DescribeVolumes"]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_instance_profile" "brain_v1" {
  name = "brain-instance-v1"
  role = aws_iam_role.brain_instance_v1.name
}

resource "aws_launch_template" "brain_v1" {
  name_prefix   = "brain-v1-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = "t4g.large"

  iam_instance_profile {
    arn = aws_iam_instance_profile.brain_v1.arn
  }

  vpc_security_group_ids = [aws_security_group.brain.id]

  user_data = base64encode(file("${path.module}/../ec2/cloud-init-v1.yaml"))

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size = 20
      volume_type = "gp3"
      encrypted   = true
      delete_on_termination = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "enabled"
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "brain-v1"
      Role = "brain-runner"
      Env  = "prod"
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_autoscaling_group" "brain_v1" {
  name                = "brain-v1"
  vpc_zone_identifier = [data.aws_subnet.first_default.id]
  desired_capacity    = 1
  min_size            = 1
  max_size            = 1
  health_check_type   = "EC2"
  health_check_grace_period = 120

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "capacity-optimized"
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.brain_v1.id
        version            = "$Latest"
      }
      override { instance_type = "t4g.large" }
    }
  }

  tag {
    key                 = "Name"
    value               = "brain-v1"
    propagate_at_launch = true
  }
}
```

- [ ] **Step 2: Add outputs**

Append to `infra/terraform/outputs.tf`:

```hcl
output "brain_asg_name" {
  value = aws_autoscaling_group.brain_v1.name
}

output "brain_launch_template_id" {
  value = aws_launch_template.brain_v1.id
}
```

- [ ] **Step 3: Plan and apply**

```bash
AWS_PROFILE=brain terraform plan -out=spot.tfplan
# Review the plan carefully — this creates the new ASG but does NOT yet retire the old on-demand instance.
AWS_PROFILE=brain terraform apply spot.tfplan
AWS_PROFILE=brain terraform output
```

Expected: ASG `brain-v1` reports `desired_capacity=1`. Within ~90s a new Spot instance appears.

- [ ] **Step 4: Smoke-check the new host**

```bash
NEW_IID=$(AWS_PROFILE=brain aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names brain-v1 \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' --output text)
echo "New instance: $NEW_IID"
AWS_PROFILE=brain aws ssm start-session --target "$NEW_IID"
# inside the instance:
#   mountpoint /var/brain   # should print: /var/brain is a mountpoint
#   ls /var/brain           # should show: vault.git worktrees db scratch config logs
#   docker ps                # should succeed (may be empty)
#   exit
```

- [ ] **Step 5: Commit**

```bash
git add infra/terraform/spot.tf infra/terraform/outputs.tf
git commit -m "infra(brain-v1): t4g.large Spot ASG + launch template + IAM"
```

---

---

## Phase C — Vault → bare repo conversion

One-time migration on the new host. Runs via SSM once; then the old on-demand instance is stopped (but not yet terminated — we keep it as a rollback safety net until Day 7).

### Task C1: Snapshot the current vault for rollback safety

**Files:** (none — operational step)

- [ ] **Step 1: Snapshot the existing EBS volume on the old host**

```bash
OLD_VOL=$(AWS_PROFILE=brain aws ec2 describe-instances \
  --instance-ids i-083850f5231bf5048 \
  --query 'Reservations[0].Instances[0].BlockDeviceMappings[0].Ebs.VolumeId' \
  --output text)
AWS_PROFILE=brain aws ec2 create-snapshot \
  --volume-id "$OLD_VOL" \
  --description "brain-v0 pre-migration snapshot $(date -u +%FT%TZ)" \
  --tag-specifications 'ResourceType=snapshot,Tags=[{Key=Name,Value=brain-v0-premigration}]'
```

Expected: command returns `SnapshotId: snap-xxx`. Record the id. Wait ~2 minutes for `State: completed`.

- [ ] **Step 2: Verify snapshot is queryable**

```bash
AWS_PROFILE=brain aws ec2 describe-snapshots \
  --filters Name=tag:Name,Values=brain-v0-premigration \
  --query 'Snapshots[0].State'
```

Expected: `"completed"`.

### Task C2: Convert vault to bare repo on the new host

**Files:** (operational; no code changes)

- [ ] **Step 1: Rsync the current vault to the new host**

From the Mac dev box:

```bash
OLD_IP=$(AWS_PROFILE=brain aws ec2 describe-instances \
  --instance-ids i-083850f5231bf5048 \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

# Pull via SSM to a temp dir on the new host. Use the AWS SSM send-command path
# (no direct ssh between EC2 instances in the default VPC without a key).
NEW_IID=$(AWS_PROFILE=brain aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names brain-v1 \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' --output text)

AWS_PROFILE=brain aws ssm send-command \
  --instance-ids "$NEW_IID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["
    set -e
    cd /var/brain
    git clone --bare https://github.com/<yogesh-user>/second-brain.git vault-clone.git
    # Keep only wiki/, raw/, jobs/ history — the vault content, not the app code
    # Actually the simpler path: use the existing repo as the bare vault too.
    # DECISION: vault.git == full second-brain repo clone (bare).
    mv vault-clone.git vault.git-new
    rm -rf vault.git
    mv vault.git-new vault.git
    cd /var/brain/vault.git
    git config gc.auto 0
    git worktree add /var/brain/worktrees/main main
    chown -R ubuntu:ubuntu /var/brain/vault.git /var/brain/worktrees
  "]' \
  --comment "brain-v1: convert vault to bare repo"
```

Expected: command returns a `CommandId`. Poll status until `Success`:

```bash
CMD=<command-id-from-above>
AWS_PROFILE=brain aws ssm list-command-invocations --command-id "$CMD" --details \
  --query 'CommandInvocations[0].Status'
```

Expected: `"Success"` within ~60s.

- [ ] **Step 2: Verify bare repo + live worktree**

```bash
AWS_PROFILE=brain aws ssm send-command \
  --instance-ids "$NEW_IID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["
    ls -la /var/brain/vault.git/HEAD /var/brain/vault.git/refs
    git -C /var/brain/worktrees/main log -1 --oneline
    git -C /var/brain/vault.git config --get gc.auto
  "]'
```

Expected: `HEAD` exists, `refs/` dir exists, `log -1` prints the latest commit, `gc.auto` returns `0`.

- [ ] **Step 3: Commit (no code change, but the ADR lands)**

This is operational — no repo change. Skip commit; log the migration in `wiki/log.md` via the next wiki maintenance pass. For the plan checklist, mark done when the smoke check passes.

### Task C3: Point brain-core at `/var/brain`

**Files:**
- Modify: `apps/brain-core/brain_core/db.py` — respect `BRAIN_DB_PATH` env var (it already does this; confirm default matches)
- Modify: `infra/ec2/systemd/brain-core.service` — set `Environment=BRAIN_DB_PATH=/var/brain/db/brain.sqlite`, `Environment=BRAIN_VAULT_PATH=/var/brain/worktrees/main`

- [ ] **Step 1: Inspect current brain-core.service**

```bash
cat /Users/yogeshseenichamy/second-brain/infra/ec2/systemd/brain-core.service
```

- [ ] **Step 2: Patch systemd unit to point at /var/brain**

Replace any existing `Environment=BRAIN_DB_PATH=...` line and add the vault path. The unit's `[Service]` section should contain:

```ini
Environment=BRAIN_DB_PATH=/var/brain/db/brain.sqlite
Environment=BRAIN_VAULT_PATH=/var/brain/worktrees/main
WorkingDirectory=/var/brain/worktrees/main
```

If the existing unit hardcodes a different path, use Edit to replace it exactly.

- [ ] **Step 3: Verify `db.py` honors the env var**

```bash
grep -n BRAIN_DB_PATH /Users/yogeshseenichamy/second-brain/apps/brain-core/brain_core/db.py
```

Expected: one line showing `os.environ.get("BRAIN_DB_PATH", ...)`. No code change needed — just confirm.

- [ ] **Step 4: Commit**

```bash
git add infra/ec2/systemd/brain-core.service
git commit -m "infra(brain-v1): brain-core systemd unit points at /var/brain for DB + vault"
```

---

## Phase D — Grafana Cloud + grafana-agent heartbeat

### Task D1: Create Grafana Cloud free-tier account + stack

**Files:** (operational; no code)

- [ ] **Step 1: Create the stack**

Go to https://grafana.com/auth/sign-up/create-user (or sign in). Create a new stack named `brain-v1` in the US East region (lowest latency to us-west-2 that the free tier supports for traces).

- [ ] **Step 2: Generate a Grafana Cloud API token**

Navigate to: My Account → Access Policies → Create access policy.
- Name: `brain-v1-writer`
- Realms: your stack
- Scopes: `metrics:write`, `logs:write`, `traces:write`
- Create token: name `brain-v1-agent`, no expiration
- Copy the token (it is shown once). Save to 1Password.

- [ ] **Step 3: Record connection details**

From the Grafana Cloud stack detail page, record:
- Prometheus `remote_write` URL and user (numeric)
- Loki push URL and user (numeric)
- Tempo OTLP HTTP URL and user (numeric)
- Single API token from Step 2 (works for all three)

Stash under `brain/grafana_cloud` in AWS Secrets Manager:

```bash
AWS_PROFILE=brain aws secretsmanager create-secret \
  --name brain/grafana_cloud \
  --description "Grafana Cloud free-tier writer creds for brain-v1" \
  --secret-string '{
    "api_token": "<paste>",
    "prom_url": "https://prometheus-prod-XX-prod-us-east-0.grafana.net/api/prom/push",
    "prom_user": "<numeric>",
    "loki_url": "https://logs-prod-XXX.grafana.net/loki/api/v1/push",
    "loki_user": "<numeric>",
    "tempo_url": "https://tempo-prod-XX-prod-us-east-0.grafana.net/tempo",
    "tempo_user": "<numeric>"
  }'
```

Expected: returns `ARN`. Record it.

### Task D2: grafana-agent config + systemd unit

**Files:**
- Create: `infra/ec2/grafana-agent.river` — grafana-agent Flow config (new format)
- Create: `infra/ec2/systemd/grafana-agent.service`

- [ ] **Step 1: Write `infra/ec2/grafana-agent.river`**

```hcl
// grafana-agent Flow config for brain-v1.
// Receives OTLP HTTP on 127.0.0.1:4318, scrapes brain-core :9100/metrics,
// tails /var/brain/logs/*.json, ships everything to Grafana Cloud.

logging {
  level  = "info"
  format = "json"
}

// --- Metrics ---------------------------------------------------------------

prometheus.remote_write "cloud" {
  endpoint {
    url = env("GRAFANA_PROM_URL")
    basic_auth {
      username = env("GRAFANA_PROM_USER")
      password = env("GRAFANA_API_TOKEN")
    }
  }
  wal {
    truncate_frequency = "2h"
    min_keepalive_time = "5m"
    max_keepalive_time = "8h"
  }
}

prometheus.scrape "brain_core" {
  targets = [
    { "__address__" = "127.0.0.1:9100", "job" = "brain-core" },
  ]
  forward_to      = [prometheus.remote_write.cloud.receiver]
  scrape_interval = "15s"
}

// --- Traces ----------------------------------------------------------------

otelcol.receiver.otlp "main" {
  http { endpoint = "127.0.0.1:4318" }
  output { traces = [otelcol.exporter.otlphttp.cloud.input] }
}

otelcol.exporter.otlphttp "cloud" {
  client {
    endpoint = env("GRAFANA_TEMPO_URL")
    auth     = otelcol.auth.basic.cloud.handler
  }
}

otelcol.auth.basic "cloud" {
  username = env("GRAFANA_TEMPO_USER")
  password = env("GRAFANA_API_TOKEN")
}

// --- Logs ------------------------------------------------------------------

local.file_match "brain_logs" {
  path_targets = [{ __path__ = "/var/brain/logs/*.json", job = "brain-core" }]
}

loki.source.file "brain_logs" {
  targets    = local.file_match.brain_logs.targets
  forward_to = [loki.write.cloud.receiver]
}

loki.write "cloud" {
  endpoint {
    url = env("GRAFANA_LOKI_URL")
    basic_auth {
      username = env("GRAFANA_LOKI_USER")
      password = env("GRAFANA_API_TOKEN")
    }
  }
}
```

- [ ] **Step 2: Write `infra/ec2/systemd/grafana-agent.service`**

```ini
[Unit]
Description=Grafana Agent (brain-v1 telemetry pipeline)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
EnvironmentFile=/etc/brain/grafana-agent.env
ExecStart=/usr/local/bin/grafana-agent run /etc/grafana-agent.river \
  --server.http.listen-addr=127.0.0.1:12345 \
  --storage.path=/var/lib/grafana-agent
Restart=always
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Install grafana-agent binary on the new host via SSM**

```bash
AWS_PROFILE=brain aws ssm send-command --instance-ids "$NEW_IID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["
    set -e
    AGENT_VERSION=0.41.1
    cd /tmp
    curl -fsSL -o grafana-agent.zip https://github.com/grafana/agent/releases/download/v${AGENT_VERSION}/grafana-agent-linux-arm64.zip
    unzip -o grafana-agent.zip
    install -m 0755 grafana-agent-linux-arm64 /usr/local/bin/grafana-agent
    mkdir -p /var/lib/grafana-agent /etc/brain
    /usr/local/bin/grafana-agent --version
  "]'
```

Expected: `Success`, version prints `v0.41.1`.

- [ ] **Step 4: Copy config + env file to the host**

First, generate the env file locally from the Secrets Manager entry:

```bash
CREDS_JSON=$(AWS_PROFILE=brain aws secretsmanager get-secret-value \
  --secret-id brain/grafana_cloud --query SecretString --output text)
cat > /tmp/grafana-agent.env <<EOF
GRAFANA_PROM_URL=$(echo "$CREDS_JSON" | jq -r .prom_url)
GRAFANA_PROM_USER=$(echo "$CREDS_JSON" | jq -r .prom_user)
GRAFANA_LOKI_URL=$(echo "$CREDS_JSON" | jq -r .loki_url)
GRAFANA_LOKI_USER=$(echo "$CREDS_JSON" | jq -r .loki_user)
GRAFANA_TEMPO_URL=$(echo "$CREDS_JSON" | jq -r .tempo_url)
GRAFANA_TEMPO_USER=$(echo "$CREDS_JSON" | jq -r .tempo_user)
GRAFANA_API_TOKEN=$(echo "$CREDS_JSON" | jq -r .api_token)
EOF
```

Then push it via SSM send-command (base64-encode the file content inline — SSM has no native file transfer, so use a heredoc with the decoded body):

```bash
B64_RIVER=$(base64 < infra/ec2/grafana-agent.river)
B64_UNIT=$(base64 < infra/ec2/systemd/grafana-agent.service)
B64_ENV=$(base64 < /tmp/grafana-agent.env)
AWS_PROFILE=brain aws ssm send-command --instance-ids "$NEW_IID" \
  --document-name "AWS-RunShellScript" \
  --parameters "commands=[\"
    echo '$B64_RIVER' | base64 -d > /etc/grafana-agent.river
    echo '$B64_UNIT'  | base64 -d > /etc/systemd/system/grafana-agent.service
    echo '$B64_ENV'   | base64 -d > /etc/brain/grafana-agent.env
    chmod 600 /etc/brain/grafana-agent.env
    systemctl daemon-reload
    systemctl enable --now grafana-agent
    sleep 3
    systemctl status grafana-agent --no-pager | head -20
  \"]"
```

Expected: `active (running)`.

- [ ] **Step 5: Verify the heartbeat reaches Grafana Cloud**

```bash
AWS_PROFILE=brain aws ssm send-command --instance-ids "$NEW_IID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=[
    "curl -s http://127.0.0.1:12345/metrics | grep -c agent_build_info",
    "journalctl -u grafana-agent -n 20 --no-pager | grep -i \"WAL\\|remote_write\" | head"
  ]'
```

Expected: `curl` returns `1` (local metrics endpoint up). Journal shows `remote_write` activity (no errors).

From the laptop, open Grafana Cloud → Explore → Prometheus datasource → query `agent_build_info`. The series should appear within 60 seconds. If yes, the pipeline is live.

- [ ] **Step 6: Commit**

```bash
git add infra/ec2/grafana-agent.river infra/ec2/systemd/grafana-agent.service
git commit -m "infra(brain-v1): grafana-agent Flow config + systemd unit for Grafana Cloud"
```

---

## Phase E — SQLite migration + run_queue + pytest setup

### Task E1: Bootstrap pytest in brain-core

**Files:**
- Modify: `apps/brain-core/pyproject.toml` — add dev deps, pytest config
- Create: `apps/brain-core/tests/__init__.py`
- Create: `apps/brain-core/tests/conftest.py`
- Create: `apps/brain-core/tests/unit/__init__.py`
- Create: `apps/brain-core/tests/integration/__init__.py`

- [ ] **Step 1: Patch `pyproject.toml`**

Append a `[project.optional-dependencies]` block and a `[tool.pytest.ini_options]` block:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "hypothesis>=6.112",
    "structlog>=24.4",
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-http>=1.27",
    "prometheus-client>=0.21",
    "jinja2>=3.1",
    "matplotlib>=3.9",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "integration: tests that spin up real SQLite/git/docker",
    "slow: tests that take >1s",
]
```

- [ ] **Step 2: Install dev deps**

```bash
cd apps/brain-core
uv sync --extra dev
```

Expected: lock file updates, all deps install.

- [ ] **Step 3: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures for brain-core unit + integration tests."""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import AsyncIterator, Iterator

import aiosqlite
import pytest


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Iterator[Path]:
    """A fresh bare git repo at tmp_path/vault.git with one initial commit
    and a long-lived worktree at tmp_path/worktrees/main."""
    bare = tmp_path / "vault.git"
    work = tmp_path / "worktrees" / "main"
    work.parent.mkdir(parents=True)

    # Seed via a scratch clone, then convert to bare
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    (seed / "README.md").write_text("seed\n")
    subprocess.run(["git", "-C", str(seed), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "seed"],
        check=True,
    )
    subprocess.run(["git", "clone", "--bare", str(seed), str(bare)], check=True)
    subprocess.run(["git", "-C", str(bare), "config", "gc.auto", "0"], check=True)
    subprocess.run(
        ["git", "-C", str(bare), "worktree", "add", str(work), "main"],
        check=True,
    )
    yield tmp_path


@pytest.fixture
async def temp_db(tmp_path: Path) -> AsyncIterator[str]:
    """A fresh SQLite DB with the v1 schema applied."""
    db_path = tmp_path / "brain.sqlite"
    os.environ["BRAIN_DB_PATH"] = str(db_path)
    from brain_core import db  # re-imported per test

    await db.init_db()
    yield str(db_path)


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[float]]:
    """Inject a mutable monotonic clock — list[0] is the current time_ns()/1e9."""
    now = [1_700_000_000.0]
    monkeypatch.setattr("time.time", lambda: now[0])
    monkeypatch.setattr("time.monotonic", lambda: now[0])
    yield now
```

- [ ] **Step 4: Sanity-run pytest (it should collect zero tests, not error)**

```bash
cd apps/brain-core
uv run pytest -q
```

Expected: `no tests ran in 0.0Xs`. No collection errors.

- [ ] **Step 5: Commit**

```bash
git add apps/brain-core/pyproject.toml apps/brain-core/uv.lock apps/brain-core/tests/
git commit -m "test(brain-core): bootstrap pytest + fixtures for v1 scheduler/sandbox work"
```

### Task E2: `run_queue` SQLite migration

**Files:**
- Create: `apps/brain-core/brain_core/migrations/__init__.py`
- Create: `apps/brain-core/brain_core/migrations/0002_run_queue.sql`
- Modify: `apps/brain-core/brain_core/db.py` — add `run_migrations()` and call it from `init_db()`

- [ ] **Step 1: Write `0002_run_queue.sql`**

```sql
-- 0002_run_queue.sql — scheduler run_queue table for brain-v1.

CREATE TABLE IF NOT EXISTS run_queue (
  id                  TEXT PRIMARY KEY,
  idempotency_key     TEXT NOT NULL,
  state               TEXT NOT NULL,            -- pending|admitted|running|reconciling|done|failed|conflicted|interrupted
  priority            INTEGER NOT NULL,         -- 1..5 (1 = CRITICAL)
  agent_class         TEXT NOT NULL,            -- chat|synthesis|ingest|background
  trigger_source      TEXT NOT NULL,            -- chat|tick|watcher|job|bench|api
  prompt_family       TEXT NOT NULL,
  payload_json        TEXT NOT NULL,            -- opaque JSON: prompt, vault_scope, model, etc.
  estimated_in        INTEGER NOT NULL DEFAULT 0,
  estimated_out       INTEGER NOT NULL DEFAULT 0,
  actual_in           INTEGER,
  actual_out          INTEGER,
  cache_read_tokens   INTEGER,
  cache_write_tokens  INTEGER,
  attempt_count       INTEGER NOT NULL DEFAULT 0,
  assigned_container  TEXT,
  worktree_path       TEXT,
  branch_name         TEXT,
  created_at          INTEGER NOT NULL,
  admitted_at         INTEGER,
  started_at          INTEGER,
  ended_at            INTEGER,
  exit_code           INTEGER,
  error_class         TEXT,
  error_detail        TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_queue_state_priority
  ON run_queue(state, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_run_queue_idempotency
  ON run_queue(idempotency_key, created_at);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version  INTEGER PRIMARY KEY,
  applied_at INTEGER NOT NULL
);
```

- [ ] **Step 2: Add `run_migrations()` to `db.py`**

Open `apps/brain-core/brain_core/db.py`. Immediately after the existing `SCHEMA = """..."""` constant, add:

```python
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def run_migrations() -> None:
    """Apply SQL files in `migrations/NNNN_*.sql` whose number > max(applied)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL);"
        )
        cur = await conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
        (current,) = await cur.fetchone()
        files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        for path in files:
            version = int(path.name[:4])
            if version <= current:
                continue
            sql = path.read_text()
            await conn.executescript(sql)
            await conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, int(time.time())),
            )
            await conn.commit()
            logger.info("applied migration %s", path.name)
```

And in the existing `init_db()` function, call `await run_migrations()` after the `executescript(SCHEMA)` call.

- [ ] **Step 3: Write `tests/unit/test_migrations.py`**

```python
import aiosqlite
import pytest

from brain_core import db


@pytest.mark.asyncio
async def test_run_queue_migration_applied(temp_db: str):
    async with aiosqlite.connect(temp_db) as conn:
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='run_queue'"
        )
        row = await cur.fetchone()
    assert row is not None, "run_queue table missing after init_db()"


@pytest.mark.asyncio
async def test_migrations_idempotent(temp_db: str):
    # Re-running migrations must not throw
    await db.run_migrations()
    await db.run_migrations()

    async with aiosqlite.connect(temp_db) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=2")
        (count,) = await cur.fetchone()
    assert count == 1
```

- [ ] **Step 4: Run tests**

```bash
cd apps/brain-core
uv run pytest tests/unit/test_migrations.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/brain-core/brain_core/db.py apps/brain-core/brain_core/migrations/ apps/brain-core/tests/unit/test_migrations.py
git commit -m "feat(brain-core): add run_queue SQLite migration + idempotent runner"
```

---

## Phase F — scheduler/ package

### Task F1: Type definitions

**Files:**
- Create: `apps/brain-core/brain_core/scheduler/__init__.py`
- Create: `apps/brain-core/brain_core/scheduler/types.py`

- [ ] **Step 1: Write `scheduler/types.py`**

```python
"""Public types for brain_core.scheduler.

These are deliberately narrow. The scheduler has a small, well-defined surface:
submit() takes a RunSpec, returns a run_id, and everything downstream reads from
the run_queue SQLite table. Tests import from here, not from internal modules.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Priority(enum.IntEnum):
    CRITICAL = 1   # chat, urgent nudges
    HIGH     = 2   # interactive /jobs/{name}/run
    NORMAL   = 3   # tick-fired runs
    LOW      = 4   # scheduled cron jobs
    BACKGROUND = 5  # lint, arxiv-digest


class AgentClass(enum.Enum):
    CHAT       = "chat"
    SYNTHESIS  = "synthesis"
    INGEST     = "ingest"
    BACKGROUND = "background"


class RunState(enum.Enum):
    PENDING      = "pending"
    ADMITTED     = "admitted"
    RUNNING      = "running"
    RECONCILING  = "reconciling"
    DONE         = "done"
    FAILED       = "failed"
    CONFLICTED   = "conflicted"
    INTERRUPTED  = "interrupted"


class TriggerSource(enum.Enum):
    CHAT    = "chat"
    TICK    = "tick"
    WATCHER = "watcher"
    JOB     = "job"
    BENCH   = "bench"
    API     = "api"


@dataclass(frozen=True)
class RunSpec:
    """Input to scheduler.submit(). Frozen so callers can't mutate mid-submit."""
    prompt: str
    prompt_family: str
    agent_class: AgentClass
    priority: Priority
    trigger_source: TriggerSource
    model: str = "claude-sonnet-4-6"
    vault_scope: tuple[str, ...] = ()   # empty = full vault
    estimated_in: int = 0
    estimated_out: int = 0
    payload_extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Run:
    """Row view of a run_queue record."""
    id: str
    idempotency_key: str
    state: RunState
    priority: Priority
    agent_class: AgentClass
    trigger_source: TriggerSource
    prompt_family: str
    payload_json: str
    estimated_in: int
    estimated_out: int
    created_at: int
    admitted_at: int | None
    started_at: int | None
    ended_at: int | None
```

- [ ] **Step 2: Write `scheduler/__init__.py`**

```python
"""brain_core.scheduler — ingress, admission, dispatch for agent runs.

Public surface:
    from brain_core.scheduler import submit, Run, RunSpec, Priority, AgentClass
"""

from .types import (
    AgentClass,
    Priority,
    Run,
    RunSpec,
    RunState,
    TriggerSource,
)
from .submit import submit

__all__ = [
    "submit",
    "Run",
    "RunSpec",
    "RunState",
    "Priority",
    "AgentClass",
    "TriggerSource",
]
```

- [ ] **Step 3: Commit**

```bash
git add apps/brain-core/brain_core/scheduler/__init__.py apps/brain-core/brain_core/scheduler/types.py
git commit -m "feat(scheduler): add type definitions (Priority, AgentClass, RunState, RunSpec, Run)"
```

### Task F2: Queue row helpers (TDD)

**Files:**
- Create: `apps/brain-core/brain_core/scheduler/queue.py`
- Create: `apps/brain-core/tests/unit/test_scheduler_queue.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_scheduler_queue.py`:

```python
import json
import pytest

from brain_core.scheduler import (
    AgentClass,
    Priority,
    RunSpec,
    RunState,
    TriggerSource,
)
from brain_core.scheduler.queue import (
    idempotency_key_for,
    insert_run,
    load_run,
    transition_state,
    list_runs_by_state,
)


def _spec() -> RunSpec:
    return RunSpec(
        prompt="hello",
        prompt_family="lc-daily",
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.LOW,
        trigger_source=TriggerSource.JOB,
        estimated_in=1000,
        estimated_out=500,
    )


def test_idempotency_key_stable_for_same_payload():
    a = idempotency_key_for(TriggerSource.JOB, {"name": "lc-daily", "date": "2026-04-14"})
    b = idempotency_key_for(TriggerSource.JOB, {"date": "2026-04-14", "name": "lc-daily"})
    assert a == b


def test_idempotency_key_differs_for_different_payload():
    a = idempotency_key_for(TriggerSource.JOB, {"name": "lc-daily", "date": "2026-04-14"})
    b = idempotency_key_for(TriggerSource.JOB, {"name": "lc-daily", "date": "2026-04-15"})
    assert a != b


@pytest.mark.asyncio
async def test_insert_then_load(temp_db: str):
    spec = _spec()
    run_id = await insert_run(spec, idempotency_key="k1")
    run = await load_run(run_id)
    assert run is not None
    assert run.id == run_id
    assert run.state == RunState.PENDING
    assert run.priority == Priority.LOW
    assert run.agent_class == AgentClass.BACKGROUND
    assert run.prompt_family == "lc-daily"
    assert run.estimated_in == 1000
    payload = json.loads(run.payload_json)
    assert payload["prompt"] == "hello"


@pytest.mark.asyncio
async def test_transition_state_updates_timestamps(temp_db: str, fake_clock):
    spec = _spec()
    run_id = await insert_run(spec, idempotency_key="k2")
    fake_clock[0] += 5
    await transition_state(run_id, RunState.ADMITTED)
    run = await load_run(run_id)
    assert run.state == RunState.ADMITTED
    assert run.admitted_at is not None


@pytest.mark.asyncio
async def test_list_runs_by_state_orders_by_priority_then_created(temp_db: str, fake_clock):
    spec_low = _spec()
    spec_high = RunSpec(
        prompt="urgent",
        prompt_family="chat",
        agent_class=AgentClass.CHAT,
        priority=Priority.CRITICAL,
        trigger_source=TriggerSource.CHAT,
    )
    id_low = await insert_run(spec_low, idempotency_key="k-low")
    fake_clock[0] += 1
    id_high = await insert_run(spec_high, idempotency_key="k-high")

    pending = await list_runs_by_state(RunState.PENDING, limit=10)
    assert [r.id for r in pending] == [id_high, id_low]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps/brain-core
uv run pytest tests/unit/test_scheduler_queue.py -v
```

Expected: `ModuleNotFoundError: brain_core.scheduler.queue` — all tests ERROR.

- [ ] **Step 3: Implement `scheduler/queue.py`**

```python
"""aiosqlite helpers for the run_queue table.

All writes go through this module; nothing else touches the raw SQL. Keeps the
SQL localized and makes it easy to add instrumentation later.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

import aiosqlite

from brain_core import db as _db
from .types import (
    AgentClass,
    Priority,
    Run,
    RunSpec,
    RunState,
    TriggerSource,
)


def idempotency_key_for(source: TriggerSource, payload: dict[str, Any]) -> str:
    """Stable hash over (trigger source, canonicalized payload).

    Payload is canonicalized via json.dumps(..., sort_keys=True) so that
    semantically identical dicts produce identical keys regardless of key order.
    """
    h = hashlib.sha256()
    h.update(source.value.encode())
    h.update(b"|")
    h.update(json.dumps(payload, sort_keys=True, default=str).encode())
    return h.hexdigest()[:32]


async def insert_run(spec: RunSpec, *, idempotency_key: str) -> str:
    run_id = str(uuid.uuid4())
    now = int(time.time())
    payload = {
        "prompt": spec.prompt,
        "model": spec.model,
        "vault_scope": list(spec.vault_scope),
        **spec.payload_extra,
    }
    async with aiosqlite.connect(_db.DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO run_queue (
                id, idempotency_key, state, priority, agent_class,
                trigger_source, prompt_family, payload_json,
                estimated_in, estimated_out, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                idempotency_key,
                RunState.PENDING.value,
                int(spec.priority),
                spec.agent_class.value,
                spec.trigger_source.value,
                spec.prompt_family,
                json.dumps(payload),
                spec.estimated_in,
                spec.estimated_out,
                now,
            ),
        )
        await conn.commit()
    return run_id


async def load_run(run_id: str) -> Run | None:
    async with aiosqlite.connect(_db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM run_queue WHERE id = ?", (run_id,))
        row = await cur.fetchone()
    return _row_to_run(row) if row else None


async def transition_state(run_id: str, new_state: RunState) -> None:
    now = int(time.time())
    ts_col = {
        RunState.ADMITTED:    "admitted_at",
        RunState.RUNNING:     "started_at",
        RunState.DONE:        "ended_at",
        RunState.FAILED:      "ended_at",
        RunState.CONFLICTED:  "ended_at",
        RunState.INTERRUPTED: "ended_at",
    }.get(new_state)

    async with aiosqlite.connect(_db.DB_PATH) as conn:
        if ts_col:
            await conn.execute(
                f"UPDATE run_queue SET state = ?, {ts_col} = COALESCE({ts_col}, ?) WHERE id = ?",
                (new_state.value, now, run_id),
            )
        else:
            await conn.execute(
                "UPDATE run_queue SET state = ? WHERE id = ?",
                (new_state.value, run_id),
            )
        await conn.commit()


async def list_runs_by_state(state: RunState, *, limit: int = 50) -> list[Run]:
    async with aiosqlite.connect(_db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM run_queue WHERE state = ? "
            "ORDER BY priority ASC, created_at ASC LIMIT ?",
            (state.value, limit),
        )
        rows = await cur.fetchall()
    return [_row_to_run(r) for r in rows]


def _row_to_run(row: aiosqlite.Row) -> Run:
    return Run(
        id=row["id"],
        idempotency_key=row["idempotency_key"],
        state=RunState(row["state"]),
        priority=Priority(row["priority"]),
        agent_class=AgentClass(row["agent_class"]),
        trigger_source=TriggerSource(row["trigger_source"]),
        prompt_family=row["prompt_family"],
        payload_json=row["payload_json"],
        estimated_in=row["estimated_in"],
        estimated_out=row["estimated_out"],
        created_at=row["created_at"],
        admitted_at=row["admitted_at"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_scheduler_queue.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/brain-core/brain_core/scheduler/queue.py apps/brain-core/tests/unit/test_scheduler_queue.py
git commit -m "feat(scheduler): queue row helpers with idempotency key hashing + unit tests"
```

### Task F3: `scheduler.submit()` public entry point (TDD)

**Files:**
- Create: `apps/brain-core/brain_core/scheduler/submit.py`
- Create: `apps/brain-core/tests/unit/test_scheduler_submit.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from brain_core.scheduler import (
    AgentClass,
    Priority,
    RunSpec,
    TriggerSource,
    submit,
)
from brain_core.scheduler.queue import load_run


def _spec(**kw) -> RunSpec:
    base = dict(
        prompt="hi",
        prompt_family="test",
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.LOW,
        trigger_source=TriggerSource.JOB,
    )
    base.update(kw)
    return RunSpec(**base)


@pytest.mark.asyncio
async def test_submit_returns_run_id(temp_db: str):
    run_id = await submit(_spec())
    assert isinstance(run_id, str) and len(run_id) == 36


@pytest.mark.asyncio
async def test_submit_persists_pending_row(temp_db: str):
    run_id = await submit(_spec())
    run = await load_run(run_id)
    assert run is not None
    assert run.prompt_family == "test"


@pytest.mark.asyncio
async def test_submit_is_idempotent_for_same_payload(temp_db: str):
    spec = _spec(payload_extra={"job_name": "lc-daily", "date": "2026-04-14"})
    first = await submit(spec)
    second = await submit(spec)
    assert first == second, "same-payload submit should return the same run_id"


@pytest.mark.asyncio
async def test_submit_new_id_for_different_payload(temp_db: str):
    first = await submit(_spec(payload_extra={"date": "2026-04-14"}))
    second = await submit(_spec(payload_extra={"date": "2026-04-15"}))
    assert first != second
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_scheduler_submit.py -v
```

Expected: `ModuleNotFoundError` or `ImportError: cannot import name 'submit'`.

- [ ] **Step 3: Implement `scheduler/submit.py`**

```python
"""scheduler.submit() — the single public ingress point for agent runs.

Every caller (chat handler, tick loop, watcher, job runner, benchmark harness)
goes through this function. No subprocess spawning, no scheduling logic — just
idempotent enqueue into run_queue. The admission loop picks up from there.
"""

from __future__ import annotations

import aiosqlite

from brain_core import db as _db
from .queue import idempotency_key_for, insert_run
from .types import RunSpec


async def submit(spec: RunSpec) -> str:
    """Enqueue a run. Idempotent on (trigger_source, payload_extra + prompt_family)."""
    key_payload = {"family": spec.prompt_family, **spec.payload_extra}
    key = idempotency_key_for(spec.trigger_source, key_payload)

    # Dedup against the last 24h of same-key rows.
    async with aiosqlite.connect(_db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT id FROM run_queue "
            "WHERE idempotency_key = ? AND created_at > strftime('%s', 'now') - 86400 "
            "ORDER BY created_at DESC LIMIT 1",
            (key,),
        )
        row = await cur.fetchone()
    if row is not None:
        return row["id"]

    return await insert_run(spec, idempotency_key=key)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_scheduler_submit.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/brain-core/brain_core/scheduler/submit.py apps/brain-core/tests/unit/test_scheduler_submit.py
git commit -m "feat(scheduler): submit() with 24h-window idempotency dedup"
```

### Task F4: Admission loop (no-op in W1)

**Files:**
- Create: `apps/brain-core/brain_core/scheduler/admission.py`
- Create: `apps/brain-core/tests/unit/test_scheduler_admission.py`

Week 1 admission is a stub: it promotes runs `pending → admitted` as long as fewer than 10 are already `admitted|running`. Bucket math lands in Week 2.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from brain_core.scheduler import (
    AgentClass,
    Priority,
    RunSpec,
    RunState,
    TriggerSource,
    submit,
)
from brain_core.scheduler.queue import list_runs_by_state
from brain_core.scheduler.admission import run_admission_pass


def _spec(family: str) -> RunSpec:
    return RunSpec(
        prompt=f"hi {family}",
        prompt_family=family,
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.NORMAL,
        trigger_source=TriggerSource.BENCH,
        payload_extra={"family": family},
    )


@pytest.mark.asyncio
async def test_admission_promotes_pending_up_to_cap(temp_db: str):
    for i in range(12):
        await submit(_spec(f"fam-{i}"))
    admitted = await run_admission_pass(max_concurrent=10)
    assert admitted == 10  # capped

    admitted_rows = await list_runs_by_state(RunState.ADMITTED)
    pending_rows = await list_runs_by_state(RunState.PENDING)
    assert len(admitted_rows) == 10
    assert len(pending_rows) == 2


@pytest.mark.asyncio
async def test_admission_respects_existing_admitted(temp_db: str):
    for i in range(3):
        await submit(_spec(f"fam-{i}"))
    await run_admission_pass(max_concurrent=10)
    for i in range(10):
        await submit(_spec(f"fam2-{i}"))
    admitted = await run_admission_pass(max_concurrent=10)
    assert admitted == 7  # 3 already admitted, 7 free slots


@pytest.mark.asyncio
async def test_admission_orders_by_priority(temp_db: str):
    await submit(RunSpec(
        prompt="low", prompt_family="low",
        agent_class=AgentClass.BACKGROUND, priority=Priority.LOW,
        trigger_source=TriggerSource.BENCH, payload_extra={"x": "low"},
    ))
    await submit(RunSpec(
        prompt="crit", prompt_family="crit",
        agent_class=AgentClass.CHAT, priority=Priority.CRITICAL,
        trigger_source=TriggerSource.CHAT, payload_extra={"x": "crit"},
    ))
    await run_admission_pass(max_concurrent=1)
    admitted_rows = await list_runs_by_state(RunState.ADMITTED)
    assert len(admitted_rows) == 1
    assert admitted_rows[0].prompt_family == "crit"
```

- [ ] **Step 2: Run tests — expect fail**

```bash
uv run pytest tests/unit/test_scheduler_admission.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `scheduler/admission.py`**

```python
"""Admission loop — W1 stub.

Promotes pending → admitted as long as total (admitted + running) < max_concurrent.
Real leaky-bucket + EWMA + per-class quotas land in Week 2 per ADR 0004.

Run states counted as 'in flight' for the cap:
    ADMITTED, RUNNING, RECONCILING
"""

from __future__ import annotations

from .queue import list_runs_by_state, transition_state
from .types import RunState

_IN_FLIGHT = (RunState.ADMITTED, RunState.RUNNING, RunState.RECONCILING)


async def run_admission_pass(*, max_concurrent: int = 10) -> int:
    in_flight = 0
    for state in _IN_FLIGHT:
        in_flight += len(await list_runs_by_state(state, limit=max_concurrent * 2))

    free = max(0, max_concurrent - in_flight)
    if free == 0:
        return 0

    pending = await list_runs_by_state(RunState.PENDING, limit=free)
    for run in pending:
        await transition_state(run.id, RunState.ADMITTED)
    return len(pending)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_scheduler_admission.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/brain-core/brain_core/scheduler/admission.py apps/brain-core/tests/unit/test_scheduler_admission.py
git commit -m "feat(scheduler): W1 stub admission (concurrency cap only) with unit tests"
```

### Task F5: Dispatch loop (no-op → sandbox wire-up lives in Phase J)

**Files:**
- Create: `apps/brain-core/brain_core/scheduler/dispatch.py`

Week 1 dispatch calls into `sandbox.lifecycle.run_one()` (implemented in Phase I) for each admitted run. Until Phase I exists, it no-ops. We wire the real call in Phase J.

- [ ] **Step 1: Write dispatch scaffold**

```python
"""Dispatch loop — picks up admitted runs and hands them to the sandbox.

In Week 1 the placement policy is FIFO. Cache-aware placement lands in Week 2.
"""

from __future__ import annotations

import asyncio
import logging

from .queue import list_runs_by_state, transition_state
from .types import Run, RunState

logger = logging.getLogger(__name__)


async def run_dispatch_pass(run_one) -> int:
    """Move admitted runs into running by handing them to `run_one(Run)`.

    `run_one` is injected so tests can pass a stub and production code passes
    `sandbox.lifecycle.run_one`.
    """
    admitted = await list_runs_by_state(RunState.ADMITTED, limit=10)
    launched = 0
    for run in admitted:
        await transition_state(run.id, RunState.RUNNING)
        asyncio.create_task(_safely_run_one(run, run_one))
        launched += 1
    return launched


async def _safely_run_one(run: Run, run_one) -> None:
    try:
        await run_one(run)
    except Exception:
        logger.exception("run_one crashed for run_id=%s", run.id)
        await transition_state(run.id, RunState.FAILED)
```

- [ ] **Step 2: Quick smoke test — stub run_one and verify state transitions**

Create `tests/unit/test_scheduler_dispatch.py`:

```python
import asyncio
import pytest

from brain_core.scheduler import (
    AgentClass,
    Priority,
    RunSpec,
    RunState,
    TriggerSource,
    submit,
)
from brain_core.scheduler.admission import run_admission_pass
from brain_core.scheduler.dispatch import run_dispatch_pass
from brain_core.scheduler.queue import load_run, transition_state


@pytest.mark.asyncio
async def test_dispatch_marks_runs_running_and_calls_run_one(temp_db: str):
    await submit(RunSpec(
        prompt="x",
        prompt_family="t",
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.LOW,
        trigger_source=TriggerSource.BENCH,
    ))
    await run_admission_pass(max_concurrent=10)

    calls = []

    async def stub_run_one(run):
        calls.append(run.id)
        await transition_state(run.id, RunState.DONE)

    await run_dispatch_pass(stub_run_one)
    await asyncio.sleep(0.05)  # let the asyncio.create_task run

    assert len(calls) == 1
    final = await load_run(calls[0])
    assert final.state == RunState.DONE
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/test_scheduler_dispatch.py -v
```

Expected: 1 test PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/brain-core/brain_core/scheduler/dispatch.py apps/brain-core/tests/unit/test_scheduler_dispatch.py
git commit -m "feat(scheduler): dispatch pass — promote admitted→running and fan out to run_one"
```

### Task F6: Scheduler runner + wire into FastAPI lifespan

**Files:**
- Create: `apps/brain-core/brain_core/scheduler/runner.py`
- Modify: `apps/brain-core/brain_core/main.py` — add lifespan hook that launches the scheduler coroutines

- [ ] **Step 1: Write `scheduler/runner.py`**

```python
"""Long-running coroutines for the scheduler loops.

start_scheduler(run_one) launches the admission and dispatch loops as background
tasks bound to the current event loop. Returns an opaque handle that can be
awaited on shutdown to cancel cleanly.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .admission import run_admission_pass
from .dispatch import run_dispatch_pass

logger = logging.getLogger(__name__)

ADMISSION_INTERVAL_SEC = 0.05  # 50ms per design D9
DISPATCH_INTERVAL_SEC  = 0.02  # 20ms


@dataclass
class SchedulerHandle:
    admission_task: asyncio.Task
    dispatch_task:  asyncio.Task

    async def stop(self) -> None:
        for t in (self.admission_task, self.dispatch_task):
            t.cancel()
        for t in (self.admission_task, self.dispatch_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


async def _admission_loop() -> None:
    while True:
        try:
            await run_admission_pass()
        except Exception:
            logger.exception("admission pass crashed")
        await asyncio.sleep(ADMISSION_INTERVAL_SEC)


async def _dispatch_loop(run_one) -> None:
    while True:
        try:
            await run_dispatch_pass(run_one)
        except Exception:
            logger.exception("dispatch pass crashed")
        await asyncio.sleep(DISPATCH_INTERVAL_SEC)


def start_scheduler(run_one) -> SchedulerHandle:
    return SchedulerHandle(
        admission_task=asyncio.create_task(_admission_loop(), name="brain.scheduler.admission"),
        dispatch_task=asyncio.create_task(_dispatch_loop(run_one), name="brain.scheduler.dispatch"),
    )
```

- [ ] **Step 2: Wire into FastAPI lifespan in `main.py`**

Read the top of `apps/brain-core/brain_core/main.py` to find the existing FastAPI app creation. At the top, import:

```python
from contextlib import asynccontextmanager
from brain_core.scheduler.runner import start_scheduler
```

Then add a lifespan context manager. For Week 1, `run_one` is a placeholder that just marks runs done (real implementation lands in Phase I):

```python
async def _placeholder_run_one(run):
    from brain_core.scheduler.queue import transition_state
    from brain_core.scheduler.types import RunState
    logger.info("placeholder run_one: marking run_id=%s DONE", run.id)
    await transition_state(run.id, RunState.DONE)


@asynccontextmanager
async def lifespan(app):
    await db.init_db()
    handle = start_scheduler(_placeholder_run_one)
    try:
        yield
    finally:
        await handle.stop()


app = FastAPI(lifespan=lifespan)
```

If `app = FastAPI(...)` already exists without a `lifespan=`, replace that single line with the `lifespan`-aware version. Do not restructure unrelated routes.

- [ ] **Step 3: Smoke test the app boots**

```bash
cd apps/brain-core
BRAIN_DB_PATH=/tmp/smoke.sqlite uv run python -m brain_core &
APP_PID=$!
sleep 2
curl -s http://127.0.0.1:8000/healthz || true
kill $APP_PID
rm -f /tmp/smoke.sqlite
```

Expected: the app boots, logs `placeholder run_one` is never called (no pending runs), shuts down cleanly.

- [ ] **Step 4: Commit**

```bash
git add apps/brain-core/brain_core/scheduler/runner.py apps/brain-core/brain_core/main.py
git commit -m "feat(scheduler): runner + FastAPI lifespan hook for admission/dispatch loops"
```

---

---

## Phase G — sandbox/worktree

### Task G1: Type definitions

**Files:**
- Create: `apps/brain-core/brain_core/sandbox/__init__.py`
- Create: `apps/brain-core/brain_core/sandbox/types.py`

- [ ] **Step 1: Write `sandbox/types.py`**

```python
"""Public types for brain_core.sandbox."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class WorktreeHandle:
    run_id: str
    worktree_path: Path
    branch_name: str
    scratch_path: Path


@dataclass(frozen=True)
class ContainerHandle:
    run_id: str
    container_id: str  # docker container id (12+ chars)


@dataclass
class RunOutcome:
    run_id: str
    exit_code: int
    final_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    stream_events: list[dict] = field(default_factory=list)
    error_class: str | None = None
    error_detail: str | None = None
```

- [ ] **Step 2: Write `sandbox/__init__.py`**

```python
"""brain_core.sandbox — per-run isolation via git worktree + docker container."""

from .types import WorktreeHandle, ContainerHandle, RunOutcome

__all__ = ["WorktreeHandle", "ContainerHandle", "RunOutcome"]
```

- [ ] **Step 3: Commit**

```bash
git add apps/brain-core/brain_core/sandbox/__init__.py apps/brain-core/brain_core/sandbox/types.py
git commit -m "feat(sandbox): type definitions (WorktreeHandle, ContainerHandle, RunOutcome)"
```

### Task G2: `sandbox/worktree.py` — prepare_run / reap_run (TDD)

**Files:**
- Create: `apps/brain-core/brain_core/sandbox/worktree.py`
- Create: `apps/brain-core/tests/unit/test_sandbox_worktree.py`

- [ ] **Step 1: Write failing tests**

```python
import asyncio
import pytest
from pathlib import Path

from brain_core.sandbox.worktree import prepare_run, reap_run
from brain_core.sandbox import WorktreeHandle


@pytest.mark.asyncio
async def test_prepare_run_creates_worktree_and_branch(temp_git_repo: Path):
    bare = temp_git_repo / "vault.git"
    handle = await prepare_run(
        run_id="abc123",
        bare_repo=bare,
        worktree_root=temp_git_repo / "worktrees",
        scratch_root=temp_git_repo / "scratch",
    )
    assert isinstance(handle, WorktreeHandle)
    assert handle.worktree_path.exists()
    assert (handle.worktree_path / "README.md").exists()
    assert handle.branch_name == "agent/run-abc123"
    assert handle.scratch_path.exists()


@pytest.mark.asyncio
async def test_reap_run_removes_worktree_and_keeps_branch(temp_git_repo: Path):
    bare = temp_git_repo / "vault.git"
    handle = await prepare_run(
        run_id="r1",
        bare_repo=bare,
        worktree_root=temp_git_repo / "worktrees",
        scratch_root=temp_git_repo / "scratch",
    )
    # Simulate an agent writing a file and committing
    (handle.worktree_path / "new.md").write_text("hello\n")
    import subprocess as sp
    sp.run(["git", "-C", str(handle.worktree_path),
            "-c", "user.email=a@a", "-c", "user.name=a",
            "add", "."], check=True)
    sp.run(["git", "-C", str(handle.worktree_path),
            "-c", "user.email=a@a", "-c", "user.name=a",
            "commit", "-qm", "agent: r1"], check=True)

    await reap_run(handle, bare_repo=bare, delete_branch=False)
    assert not handle.worktree_path.exists()
    # Branch preserved for the reconciler in the fail path
    branches = sp.check_output(["git", "-C", str(bare), "branch"]).decode()
    assert "agent/run-r1" in branches


@pytest.mark.asyncio
async def test_reap_run_deletes_branch_when_requested(temp_git_repo: Path):
    bare = temp_git_repo / "vault.git"
    handle = await prepare_run(
        run_id="r2",
        bare_repo=bare,
        worktree_root=temp_git_repo / "worktrees",
        scratch_root=temp_git_repo / "scratch",
    )
    await reap_run(handle, bare_repo=bare, delete_branch=True)
    import subprocess as sp
    branches = sp.check_output(["git", "-C", str(bare), "branch"]).decode()
    assert "agent/run-r2" not in branches
```

- [ ] **Step 2: Run tests — expect fail**

```bash
uv run pytest tests/unit/test_sandbox_worktree.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `sandbox/worktree.py`**

```python
"""Git-worktree lifecycle for one run.

prepare_run() creates /var/brain/worktrees/run-<id>/ on a fresh branch
agent/run-<id>, branched from main. reap_run() removes the worktree and
optionally deletes the branch (merged runs delete; failed/conflicted runs
keep the branch alive for the reconciler).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .types import WorktreeHandle


async def prepare_run(
    *,
    run_id: str,
    bare_repo: Path,
    worktree_root: Path,
    scratch_root: Path,
) -> WorktreeHandle:
    worktree_path = worktree_root / f"run-{run_id}"
    scratch_path  = scratch_root  / f"run-{run_id}"
    branch_name   = f"agent/run-{run_id}"

    scratch_path.mkdir(parents=True, exist_ok=True)

    await _git(bare_repo,
        "worktree", "add", "-b", branch_name, str(worktree_path), "main")

    return WorktreeHandle(
        run_id=run_id,
        worktree_path=worktree_path,
        branch_name=branch_name,
        scratch_path=scratch_path,
    )


async def reap_run(
    handle: WorktreeHandle,
    *,
    bare_repo: Path,
    delete_branch: bool,
) -> None:
    # Force is required because uncommitted changes in the worktree are
    # recoverable via the branch; the worktree directory itself is disposable.
    await _git(bare_repo, "worktree", "remove", "--force", str(handle.worktree_path))
    if delete_branch:
        await _git(bare_repo, "branch", "-D", handle.branch_name)

    # Clean up scratch (best-effort)
    import shutil
    shutil.rmtree(handle.scratch_path, ignore_errors=True)


async def _git(cwd: Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(cwd), *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({proc.returncode}): {stderr.decode()}"
        )
    return stdout.decode()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_sandbox_worktree.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/brain-core/brain_core/sandbox/worktree.py apps/brain-core/tests/unit/test_sandbox_worktree.py
git commit -m "feat(sandbox): prepare_run/reap_run git worktree lifecycle + unit tests"
```

---

## Phase H — brain-worker Docker image + ECR push

### Task H1: Dockerfile + entrypoint

**Files:**
- Create: `infra/docker/brain-worker/Dockerfile`
- Create: `infra/docker/brain-worker/run-agent.sh`
- Create: `infra/docker/brain-worker/requirements.txt`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
# brain-worker:v1 — ARM64 sandbox image for per-run claude -p execution.
# Built for linux/arm64 (t4g.large host). See ADR 0001 + 0005.

FROM python:3.12-slim-bookworm

# System deps: git (reconciler reads the repo inside the sandbox for some
# job prompts), curl (local policy proxy calls in W2), ca-certs.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the Anthropic Claude CLI. Version pinned; update deliberately.
ENV CLAUDE_VERSION=1.0.0
RUN curl -fsSL "https://claude.ai/install.sh" | bash -s -- --yes \
    && /root/.local/bin/claude --version \
    && cp /root/.local/bin/claude /usr/local/bin/claude

# Python deps needed inside the sandbox (none for W1 beyond the Claude CLI).
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY run-agent.sh /usr/local/bin/run-agent.sh
RUN chmod +x /usr/local/bin/run-agent.sh

# The worktree is bind-mounted at /workspace; scratch at /scratch.
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/run-agent.sh"]
```

- [ ] **Step 2: Write `run-agent.sh`**

```bash
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
```

- [ ] **Step 3: Write `requirements.txt`**

```text
# brain-worker W1 has no Python deps beyond what the base image + claude CLI bundle.
# W2 adds httpx for the local policy proxy client.
```

(An empty-ish file is intentional — `pip install -r` is a no-op but leaves the hook in place for W2.)

- [ ] **Step 4: Commit**

```bash
git add infra/docker/brain-worker/
git commit -m "infra(brain-v1): brain-worker:v1 Dockerfile + entrypoint (ARM64)"
```

### Task H2: Build and push to ECR

**Files:**
- Create: `infra/docker/brain-worker/build-and-push.sh`

- [ ] **Step 1: Write `build-and-push.sh`**

```bash
#!/usr/bin/env bash
# Build brain-worker:vN for linux/arm64 and push to ECR.
# Requires: docker buildx enabled, AWS_PROFILE=brain, ECR repo already created.
set -euo pipefail

VERSION="${1:-v1}"
REGION="${AWS_REGION:-us-west-2}"
PROFILE="${AWS_PROFILE:-brain}"

ACCOUNT=$(AWS_PROFILE="$PROFILE" aws sts get-caller-identity --query Account --output text)
REPO="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/brain/brain-worker"
TAG="${REPO}:${VERSION}"

echo "=> Authenticating with ECR"
AWS_PROFILE="$PROFILE" aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

echo "=> Building brain-worker:${VERSION} for linux/arm64"
cd "$(dirname "$0")"
docker buildx create --use --name brain-builder >/dev/null 2>&1 || docker buildx use brain-builder
docker buildx build \
  --platform linux/arm64 \
  --tag "$TAG" \
  --push \
  .

echo "=> Verifying image in ECR"
AWS_PROFILE="$PROFILE" aws ecr describe-images \
  --repository-name brain/brain-worker \
  --image-ids imageTag="$VERSION" \
  --query 'imageDetails[0].imagePushedAt' --output text

echo "=> Pushed: $TAG"
```

- [ ] **Step 2: Run the build from the Mac (requires buildx + Docker Desktop)**

```bash
chmod +x infra/docker/brain-worker/build-and-push.sh
AWS_PROFILE=brain ./infra/docker/brain-worker/build-and-push.sh v1
```

Expected: buildx builds the ARM64 image, pushes to ECR, prints the push timestamp.

- [ ] **Step 3: Verify on the EC2 host it can pull**

```bash
AWS_PROFILE=brain aws ssm send-command --instance-ids "$NEW_IID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["
    ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    REGION=us-west-2
    aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin ${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com
    docker pull ${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/brain/brain-worker:v1
    docker images | grep brain-worker
  "]'
```

Expected: pull succeeds, image appears in `docker images`.

- [ ] **Step 4: Commit**

```bash
git add infra/docker/brain-worker/build-and-push.sh
git commit -m "infra(brain-v1): build-and-push script for brain-worker ECR image"
```

### Task H3: Create the `brain-runs` docker network on the host

**Files:** (operational — command runs once on the host, persisted via systemd)

- [ ] **Step 1: Create the network via SSM**

```bash
AWS_PROFILE=brain aws ssm send-command --instance-ids "$NEW_IID" \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["
    docker network inspect brain-runs >/dev/null 2>&1 || \
      docker network create --driver bridge brain-runs
    docker network inspect brain-runs --format \"{{.Name}}: {{.Driver}}\"
  "]'
```

Expected: `brain-runs: bridge`. The egress allowlist lands in Week 2 (ADR 0006 autonomy-policy-split references it). For W1 the network is fully open — this is acceptable because the sandbox has no API keys except the mounted Claude credentials.

- [ ] **Step 2: Log the step in the ADR trail**

(Operational only — no repo change; the network state is captured in `infra/ec2/cloud-init-v1.yaml` in a later pass if needed.)

---

## Phase I — sandbox/container + sandbox/exec

### Task I1: `sandbox/container.py` — docker run wrapper

**Files:**
- Create: `apps/brain-core/brain_core/sandbox/container.py`

Integration tests for this module run against real Docker and are marked `@pytest.mark.integration`. Unit tests mock `asyncio.create_subprocess_exec`.

- [ ] **Step 1: Write unit test for the docker arg construction**

Create `tests/unit/test_sandbox_container_args.py`:

```python
from pathlib import Path
from brain_core.sandbox.container import build_docker_run_args


def test_args_include_resource_caps(tmp_path: Path):
    args = build_docker_run_args(
        run_id="r1",
        image="brain-worker:v1",
        worktree_path=tmp_path / "wt",
        scratch_path=tmp_path / "sc",
        prompt="hi",
        prompt_family="t",
        model="claude-sonnet-4-6",
    )
    joined = " ".join(args)
    assert "--cpus=1.0" in joined
    assert "--memory=512m" in joined
    assert "--pids-limit=256" in joined
    assert "--network=brain-runs" in joined
    assert "--security-opt no-new-privileges" in joined
    assert "--cap-drop=ALL" in joined
    assert str(tmp_path / "wt") in joined
    assert "BRAIN_RUN_ID=r1" in joined
    assert "BRAIN_PROMPT_FAMILY=t" in joined
    assert "brain-worker:v1" in joined


def test_args_envvars_are_individual_flags(tmp_path: Path):
    args = build_docker_run_args(
        run_id="r1",
        image="brain-worker:v1",
        worktree_path=tmp_path / "wt",
        scratch_path=tmp_path / "sc",
        prompt="hi",
        prompt_family="t",
        model="claude-sonnet-4-6",
    )
    # Each env var is passed as two args: "-e", "KEY=VALUE"
    env_flags = [i for i, a in enumerate(args) if a == "-e"]
    env_vars = [args[i + 1] for i in env_flags]
    assert any(v.startswith("BRAIN_RUN_ID=") for v in env_vars)
    assert any(v.startswith("BRAIN_PROMPT=") for v in env_vars)
```

- [ ] **Step 2: Run tests — expect fail**

```bash
uv run pytest tests/unit/test_sandbox_container_args.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `sandbox/container.py`**

```python
"""Docker container lifecycle for one sandboxed run.

Week 1 form: fire-and-forget docker run + stream attach via the Docker CLI's
`docker run` with stdout piped to the caller. We intentionally avoid the Docker
SDK for W1 because subprocess + stream-json is exactly how v0 brain-core runs
claude -p already — keeping the mental model consistent lowers risk.

W2 adds the local policy proxy + network egress allowlist.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

from .types import ContainerHandle

logger = logging.getLogger(__name__)


def build_docker_run_args(
    *,
    run_id: str,
    image: str,
    worktree_path: Path,
    scratch_path: Path,
    prompt: str,
    prompt_family: str,
    model: str,
) -> list[str]:
    return [
        "docker", "run", "--rm", "-i",
        "--name", f"brain-run-{run_id}",
        "--cpus=1.0",
        "--memory=512m",
        "--memory-swap=512m",
        "--pids-limit=256",
        "--network=brain-runs",
        "--security-opt", "no-new-privileges",
        "--cap-drop=ALL",
        "--mount", f"type=bind,src={worktree_path},dst=/workspace",
        "--mount", f"type=bind,src={scratch_path},dst=/scratch",
        "-e", f"BRAIN_RUN_ID={run_id}",
        "-e", f"BRAIN_PROMPT={prompt}",
        "-e", f"BRAIN_PROMPT_FAMILY={prompt_family}",
        "-e", f"BRAIN_MODEL={model}",
        image,
    ]


async def start_run(
    *,
    run_id: str,
    image: str,
    worktree_path: Path,
    scratch_path: Path,
    prompt: str,
    prompt_family: str,
    model: str,
) -> tuple[ContainerHandle, AsyncIterator[bytes], asyncio.subprocess.Process]:
    """Start the container and return (handle, stdout_stream, process).

    The caller is responsible for iterating stdout_stream until exhaustion and
    awaiting proc.wait() to get the exit code. Use sandbox.exec.stream_run() as
    the glue.
    """
    args = build_docker_run_args(
        run_id=run_id,
        image=image,
        worktree_path=worktree_path,
        scratch_path=scratch_path,
        prompt=prompt,
        prompt_family=prompt_family,
        model=model,
    )
    logger.info("starting sandbox run_id=%s image=%s", run_id, image)

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def stdout_iter() -> AsyncIterator[bytes]:
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield line

    return ContainerHandle(run_id=run_id, container_id=f"brain-run-{run_id}"), stdout_iter(), proc


async def stop_run(handle: ContainerHandle) -> None:
    proc = await asyncio.create_subprocess_exec(
        "docker", "kill", handle.container_id,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_sandbox_container_args.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/brain-core/brain_core/sandbox/container.py apps/brain-core/tests/unit/test_sandbox_container_args.py
git commit -m "feat(sandbox): docker run wrapper with cgroup limits + unit tests for arg construction"
```

### Task I2: `sandbox/exec.py` — stream-json parser

**Files:**
- Create: `apps/brain-core/brain_core/sandbox/exec.py`
- Create: `apps/brain-core/tests/unit/test_sandbox_exec.py`

- [ ] **Step 1: Write failing tests with a recorded stream fixture**

```python
import json
import pytest

from brain_core.sandbox.exec import parse_stream_json, StreamParseResult


def _lines(events: list[dict]) -> list[bytes]:
    return [(json.dumps(e) + "\n").encode() for e in events]


def test_parse_captures_final_text_and_usage():
    events = [
        {"type": "message_start", "message": {"id": "m1"}},
        {"type": "stream_event", "event": {"type": "content_block_start",
            "content_block": {"type": "text", "text": ""}}},
        {"type": "stream_event", "event": {"type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Hello "}}},
        {"type": "stream_event", "event": {"type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "world"}}},
        {"type": "result", "result": "Hello world",
         "usage": {"input_tokens": 42, "output_tokens": 7,
                   "cache_read_input_tokens": 30, "cache_creation_input_tokens": 0}},
    ]
    result = parse_stream_json(_lines(events))
    assert isinstance(result, StreamParseResult)
    assert result.final_text == "Hello world"
    assert result.input_tokens == 42
    assert result.output_tokens == 7
    assert result.cache_read_tokens == 30
    assert result.cache_write_tokens == 0
    assert len(result.events) == 5


def test_parse_tolerates_garbage_lines():
    lines = [
        b"not-json\n",
        b'{"type": "result", "result": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}\n',
    ]
    result = parse_stream_json(lines)
    assert result.final_text == "ok"
    # Garbage lines are skipped, not fatal
    assert result.input_tokens == 1
```

- [ ] **Step 2: Run tests — expect fail**

```bash
uv run pytest tests/unit/test_sandbox_exec.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement `sandbox/exec.py`**

```python
"""Parse stream-json output from a containerized claude -p run.

The host iterates the container's stdout line-by-line, feeds lines through
parse_stream_json(), and collects a StreamParseResult. Each line is a JSON
envelope; we care about two kinds: text deltas for progressive fan-out, and
the final `result` event for the token usage block.

Tool-use and thinking blocks are observed but not surfaced in W1 — they become
spans in W2 once the decorator-driven instrumentation lands.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass
class StreamParseResult:
    final_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    events: list[dict] = field(default_factory=list)


def parse_stream_json(lines: Iterable[bytes]) -> StreamParseResult:
    result = StreamParseResult()
    accumulated_deltas: list[str] = []

    for raw in lines:
        try:
            event = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.debug("skipping non-JSON stream line: %r", raw[:200])
            continue

        result.events.append(event)
        etype = event.get("type")

        if etype == "stream_event":
            inner = event.get("event", {})
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta":
                    accumulated_deltas.append(delta.get("text", ""))

        elif etype == "result":
            result.final_text = event.get("result") or "".join(accumulated_deltas)
            usage = event.get("usage") or {}
            result.input_tokens  = int(usage.get("input_tokens", 0))
            result.output_tokens = int(usage.get("output_tokens", 0))
            result.cache_read_tokens  = int(usage.get("cache_read_input_tokens", 0))
            result.cache_write_tokens = int(usage.get("cache_creation_input_tokens", 0))

    if not result.final_text and accumulated_deltas:
        result.final_text = "".join(accumulated_deltas)

    return result
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_sandbox_exec.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/brain-core/brain_core/sandbox/exec.py apps/brain-core/tests/unit/test_sandbox_exec.py
git commit -m "feat(sandbox): stream-json parser with usage capture + unit tests"
```

### Task I3: `sandbox/lifecycle.py` — glue: prepare → start → stream → reap

**Files:**
- Create: `apps/brain-core/brain_core/sandbox/lifecycle.py`

- [ ] **Step 1: Write `sandbox/lifecycle.py`**

```python
"""run_one(Run) — the sandbox-side entry point the dispatch loop calls.

Flow:
    1. prepare_run() creates the worktree + branch
    2. start_run() launches the docker container
    3. parse_stream_json() drains stdout
    4. sandbox returns the outcome to the caller (reconciler runs next)
    5. reap_run() is called by the caller after reconcile
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .container import start_run
from .exec import parse_stream_json
from .types import RunOutcome, WorktreeHandle
from .worktree import prepare_run, reap_run

logger = logging.getLogger(__name__)


BARE_REPO     = Path(os.environ.get("BRAIN_VAULT_GIT",  "/var/brain/vault.git"))
WORKTREE_ROOT = Path(os.environ.get("BRAIN_WORKTREE_ROOT", "/var/brain/worktrees"))
SCRATCH_ROOT  = Path(os.environ.get("BRAIN_SCRATCH_ROOT",  "/var/brain/scratch"))
WORKER_IMAGE  = os.environ.get("BRAIN_WORKER_IMAGE", "brain-worker:v1")


async def execute(*, run_id: str, prompt: str, prompt_family: str, model: str
                  ) -> tuple[WorktreeHandle, RunOutcome]:
    """Prepare, start, stream, return. The caller is responsible for reconcile + reap."""
    handle = await prepare_run(
        run_id=run_id,
        bare_repo=BARE_REPO,
        worktree_root=WORKTREE_ROOT,
        scratch_root=SCRATCH_ROOT,
    )

    _, stdout_iter, proc = await start_run(
        run_id=run_id,
        image=WORKER_IMAGE,
        worktree_path=handle.worktree_path,
        scratch_path=handle.scratch_path,
        prompt=prompt,
        prompt_family=prompt_family,
        model=model,
    )

    lines: list[bytes] = []
    async for line in stdout_iter:
        lines.append(line)

    exit_code = await proc.wait()
    stderr = (await proc.stderr.read()).decode() if proc.stderr else ""

    parsed = parse_stream_json(lines)

    outcome = RunOutcome(
        run_id=run_id,
        exit_code=exit_code,
        final_text=parsed.final_text,
        input_tokens=parsed.input_tokens,
        output_tokens=parsed.output_tokens,
        cache_read_tokens=parsed.cache_read_tokens,
        cache_write_tokens=parsed.cache_write_tokens,
        stream_events=parsed.events,
        error_detail=stderr if exit_code != 0 else None,
        error_class="docker_nonzero_exit" if exit_code != 0 else None,
    )
    return handle, outcome
```

- [ ] **Step 2: Commit**

```bash
git add apps/brain-core/brain_core/sandbox/lifecycle.py
git commit -m "feat(sandbox): execute() glue for prepare → start → stream → return"
```

---

## Phase J — End-to-end wiring

### Task J1: Replace placeholder `run_one` with the real sandbox+reconciler path

**Files:**
- Modify: `apps/brain-core/brain_core/main.py` — wire `run_one` to call `sandbox.execute` then `reconciler.merge.fast_forward_or_stage` (reconciler lands in Phase K; until then, use a no-op reconcile that just marks `DONE`)
- Create: `apps/brain-core/brain_core/scheduler/run_one.py` — the real per-run coroutine

- [ ] **Step 1: Write `scheduler/run_one.py`**

```python
"""Per-run coroutine called by dispatch for each admitted run.

This is the composition root for sandbox + reconciler. Keeping it in scheduler/
(not sandbox/) because the scheduler owns the run_queue state machine, not the
sandbox; moving the state transitions here isolates sandbox from the DB.
"""

from __future__ import annotations

import json
import logging

from brain_core.sandbox import lifecycle
from .queue import load_run, transition_state
from .types import Run, RunState

logger = logging.getLogger(__name__)


async def run_one(run: Run) -> None:
    fresh = await load_run(run.id)
    if fresh is None or fresh.state != RunState.RUNNING:
        logger.warning("run_one: unexpected state for run_id=%s state=%s",
                       run.id, fresh.state if fresh else None)
        return

    payload = json.loads(fresh.payload_json)
    prompt = payload.get("prompt", "")
    model  = payload.get("model", "claude-sonnet-4-6")

    try:
        handle, outcome = await lifecycle.execute(
            run_id=fresh.id,
            prompt=prompt,
            prompt_family=fresh.prompt_family,
            model=model,
        )
    except Exception:
        logger.exception("sandbox.execute crashed for run_id=%s", fresh.id)
        await transition_state(fresh.id, RunState.FAILED)
        return

    await transition_state(fresh.id, RunState.RECONCILING)

    # Phase K wires reconciler.merge here. Until then: optimistic DONE.
    try:
        from brain_core.reconciler.merge import fast_forward_or_stage
        from brain_core.sandbox.worktree import reap_run
        from brain_core.sandbox.lifecycle import BARE_REPO

        outcome_state = await fast_forward_or_stage(handle, outcome, bare_repo=BARE_REPO)
        await reap_run(handle, bare_repo=BARE_REPO,
                       delete_branch=(outcome_state == RunState.DONE))
        await transition_state(fresh.id, outcome_state)
    except ImportError:
        # Reconciler not yet in place — W1 Phase I → J bridge
        await transition_state(fresh.id, RunState.DONE)
```

- [ ] **Step 2: Replace placeholder in `main.py`**

Find the `_placeholder_run_one` function in `main.py` and delete it. In the lifespan, replace `start_scheduler(_placeholder_run_one)` with:

```python
from brain_core.scheduler.run_one import run_one
...
handle = start_scheduler(run_one)
```

- [ ] **Step 3: Commit**

```bash
git add apps/brain-core/brain_core/scheduler/run_one.py apps/brain-core/brain_core/main.py
git commit -m "feat(scheduler): wire dispatch → sandbox.execute → reconciler via run_one()"
```

### Task J2: Integration test — end-to-end run against a fake claude worker

**Files:**
- Create: `apps/brain-core/tests/integration/conftest.py`
- Create: `apps/brain-core/tests/integration/fake_brain_worker/Dockerfile`
- Create: `apps/brain-core/tests/integration/fake_brain_worker/fake-claude.sh`
- Create: `apps/brain-core/tests/integration/test_end_to_end_run.py`

**Why a fake worker:** testing against the real Anthropic API in CI is flaky, expensive, and not what we're validating — we're validating that scheduler + sandbox + reconciler glue works end-to-end. The fake worker is a 10-line shell script that emits a canned stream-json blob and writes one file into `/workspace`.

- [ ] **Step 1: Write `fake_brain_worker/Dockerfile`**

```dockerfile
FROM alpine:3.20
RUN apk add --no-cache bash git
COPY fake-claude.sh /usr/local/bin/fake-claude
RUN chmod +x /usr/local/bin/fake-claude
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/fake-claude"]
```

- [ ] **Step 2: Write `fake_brain_worker/fake-claude.sh`**

```bash
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
```

- [ ] **Step 3: Write `integration/conftest.py`**

```python
import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fake_worker_image() -> str:
    here = Path(__file__).parent / "fake_brain_worker"
    tag = "brain-worker-fake:test"
    subprocess.run(
        ["docker", "build", "--tag", tag, str(here)],
        check=True,
    )
    yield tag


@pytest.fixture
def brain_runs_network() -> str:
    name = "brain-runs"
    subprocess.run(
        ["docker", "network", "inspect", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # create if missing (best-effort; errors OK if already exists)
    subprocess.run(
        ["docker", "network", "create", "--driver", "bridge", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return name
```

- [ ] **Step 4: Write `integration/test_end_to_end_run.py`**

```python
import asyncio
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_end_to_end_run_completes(
    temp_db: str,
    temp_git_repo: Path,
    fake_worker_image: str,
    brain_runs_network: str,
):
    os.environ["BRAIN_VAULT_GIT"]      = str(temp_git_repo / "vault.git")
    os.environ["BRAIN_WORKTREE_ROOT"]  = str(temp_git_repo / "worktrees")
    os.environ["BRAIN_SCRATCH_ROOT"]   = str(temp_git_repo / "scratch")
    os.environ["BRAIN_WORKER_IMAGE"]   = fake_worker_image

    # Re-import lifecycle to pick up env-derived module-level constants
    import importlib
    from brain_core.sandbox import lifecycle
    importlib.reload(lifecycle)

    from brain_core.scheduler import (
        AgentClass, Priority, RunSpec, RunState, TriggerSource, submit,
    )
    from brain_core.scheduler.admission import run_admission_pass
    from brain_core.scheduler.dispatch import run_dispatch_pass
    from brain_core.scheduler.queue import load_run
    from brain_core.scheduler.run_one import run_one

    run_id = await submit(RunSpec(
        prompt="say hi",
        prompt_family="smoke",
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.BACKGROUND,
        trigger_source=TriggerSource.BENCH,
    ))

    await run_admission_pass(max_concurrent=5)
    await run_dispatch_pass(run_one)

    # Wait for the run_one task to finish (container start + stream + reap)
    deadline = asyncio.get_event_loop().time() + 60
    while asyncio.get_event_loop().time() < deadline:
        row = await load_run(run_id)
        if row.state in (RunState.DONE, RunState.FAILED, RunState.CONFLICTED):
            break
        await asyncio.sleep(0.5)

    row = await load_run(run_id)
    assert row.state == RunState.DONE, f"final state: {row.state}"
```

- [ ] **Step 5: Run the integration test locally**

Requires Docker Desktop (or an arm64 runtime) on the Mac:

```bash
cd apps/brain-core
uv run pytest tests/integration/test_end_to_end_run.py -v -m integration
```

Expected: one test PASSES. Runtime ~15–25 seconds (image build is cached on repeat runs).

- [ ] **Step 6: Commit**

```bash
git add apps/brain-core/tests/integration/
git commit -m "test(brain-core): end-to-end integration test with fake_brain_worker"
```

---

## Phase K — reconciler/ fast-forward

### Task K1: Types + fast-forward merge (TDD)

**Files:**
- Create: `apps/brain-core/brain_core/reconciler/__init__.py`
- Create: `apps/brain-core/brain_core/reconciler/types.py`
- Create: `apps/brain-core/brain_core/reconciler/merge.py`
- Create: `apps/brain-core/tests/unit/test_reconciler_merge.py`

- [ ] **Step 1: Write `reconciler/types.py`**

```python
from __future__ import annotations

import enum


class ReconcileOutcome(enum.Enum):
    MERGED_FF     = "merged_ff"
    MERGED_THREEWAY = "merged_threeway"
    CONFLICTED    = "conflicted"
    FAILED        = "failed"
```

- [ ] **Step 2: Write `reconciler/__init__.py`**

```python
"""brain_core.reconciler — merge run branches back to main."""

from .types import ReconcileOutcome

__all__ = ["ReconcileOutcome"]
```

- [ ] **Step 3: Write failing tests**

```python
import subprocess
from pathlib import Path

import pytest

from brain_core.reconciler.merge import fast_forward_or_stage
from brain_core.reconciler.types import ReconcileOutcome
from brain_core.sandbox.types import RunOutcome, WorktreeHandle
from brain_core.scheduler.types import RunState


def _seed_worktree_with_commit(temp_git_repo: Path, run_id: str) -> WorktreeHandle:
    bare = temp_git_repo / "vault.git"
    wt = temp_git_repo / "worktrees" / f"run-{run_id}"
    branch = f"agent/run-{run_id}"
    subprocess.run(
        ["git", "-C", str(bare), "worktree", "add", "-b", branch, str(wt), "main"],
        check=True,
    )
    (wt / f"{run_id}.md").write_text("agent wrote this\n")
    subprocess.run(
        ["git", "-C", str(wt), "-c", "user.email=a@a", "-c", "user.name=a", "add", "."],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(wt), "-c", "user.email=a@a", "-c", "user.name=a",
         "commit", "-qm", f"agent: {run_id}"],
        check=True,
    )
    return WorktreeHandle(
        run_id=run_id,
        worktree_path=wt,
        branch_name=branch,
        scratch_path=temp_git_repo / "scratch" / f"run-{run_id}",
    )


def _outcome(run_id: str, exit_code: int = 0) -> RunOutcome:
    return RunOutcome(run_id=run_id, exit_code=exit_code, final_text="ok")


@pytest.mark.asyncio
async def test_fast_forward_success_returns_done(temp_git_repo: Path):
    handle = _seed_worktree_with_commit(temp_git_repo, "ff1")
    outcome = _outcome("ff1")
    state = await fast_forward_or_stage(
        handle, outcome, bare_repo=temp_git_repo / "vault.git"
    )
    assert state == RunState.DONE

    # main now contains the new file
    main_wt = temp_git_repo / "worktrees" / "main"
    assert (main_wt / "ff1.md").exists()


@pytest.mark.asyncio
async def test_nonff_returns_conflicted_and_preserves_branch(temp_git_repo: Path):
    bare = temp_git_repo / "vault.git"
    main_wt = temp_git_repo / "worktrees" / "main"

    # Diverge main so fast-forward is impossible
    (main_wt / "shared.md").write_text("main version\n")
    subprocess.run(
        ["git", "-C", str(main_wt), "-c", "user.email=m@m", "-c", "user.name=m",
         "add", "."], check=True,
    )
    subprocess.run(
        ["git", "-C", str(main_wt), "-c", "user.email=m@m", "-c", "user.name=m",
         "commit", "-qm", "main divergent commit"], check=True,
    )

    handle = _seed_worktree_with_commit(temp_git_repo, "nf1")
    outcome = _outcome("nf1")

    state = await fast_forward_or_stage(handle, outcome, bare_repo=bare)
    assert state == RunState.CONFLICTED

    branches = subprocess.check_output(["git", "-C", str(bare), "branch"]).decode()
    assert "agent/run-nf1" in branches


@pytest.mark.asyncio
async def test_failed_outcome_does_not_merge(temp_git_repo: Path):
    handle = _seed_worktree_with_commit(temp_git_repo, "fail1")
    outcome = _outcome("fail1", exit_code=2)
    state = await fast_forward_or_stage(
        handle, outcome, bare_repo=temp_git_repo / "vault.git"
    )
    assert state == RunState.FAILED
```

- [ ] **Step 4: Run tests — expect fail**

```bash
uv run pytest tests/unit/test_reconciler_merge.py -v
```

Expected: `ModuleNotFoundError` on `reconciler.merge`.

- [ ] **Step 5: Implement `reconciler/merge.py`**

```python
"""Fast-forward reconciler for W1.

Three-way merge and conflict-draft filing land in W2 (ADR 0001 follow-up).
For W1: if the run produced a non-zero exit code → FAILED. Else try
fast-forward. Success → DONE. Non-ff → CONFLICTED (branch preserved for
the W2 three-way path or manual resolution).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from brain_core.sandbox.types import RunOutcome, WorktreeHandle
from brain_core.scheduler.types import RunState

logger = logging.getLogger(__name__)


async def fast_forward_or_stage(
    handle: WorktreeHandle,
    outcome: RunOutcome,
    *,
    bare_repo: Path,
) -> RunState:
    if outcome.exit_code != 0:
        logger.info("reconciler: run %s failed (exit=%s) — skipping merge",
                    handle.run_id, outcome.exit_code)
        return RunState.FAILED

    main_worktree = bare_repo.parent / "worktrees" / "main"

    try:
        await _git(main_worktree, "merge", "--ff-only", handle.branch_name)
    except RuntimeError as err:
        logger.info("reconciler: fast-forward failed for %s — %s",
                    handle.run_id, err)
        return RunState.CONFLICTED

    logger.info("reconciler: fast-forward succeeded for %s", handle.run_id)
    return RunState.DONE


async def _git(cwd: Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(cwd), *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({proc.returncode}): {stderr.decode()}"
        )
    return stdout.decode()
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/unit/test_reconciler_merge.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/brain-core/brain_core/reconciler/ apps/brain-core/tests/unit/test_reconciler_merge.py
git commit -m "feat(reconciler): fast-forward merge path + unit tests (three-way W2)"
```

### Task K2: Stub three-way and conflict paths with explicit NotImplementedError

**Files:**
- Create: `apps/brain-core/brain_core/reconciler/three_way.py`
- Create: `apps/brain-core/brain_core/reconciler/conflicts.py`

Why stubs instead of nothing: the call sites (W2 admission controller, conflict inbox) are easier to wire correctly when the shape of the API exists. `NotImplementedError` is explicit and fails loud.

- [ ] **Step 1: Write `reconciler/three_way.py`**

```python
"""Three-way merge path — W2 implementation (ADR 0001 follow-up).

Takes a run's branch and attempts a non-ff merge into main. On success:
(MERGED_THREEWAY, merge commit SHA). On conflict: (CONFLICTED, set of
conflicted file paths) — caller then files a conflict draft.
"""

from __future__ import annotations

from pathlib import Path

from brain_core.sandbox.types import WorktreeHandle
from .types import ReconcileOutcome


async def three_way_merge(
    handle: WorktreeHandle,
    *,
    bare_repo: Path,
) -> tuple[ReconcileOutcome, list[str]]:
    raise NotImplementedError("three-way merge is a Week 2 deliverable (ADR 0001 follow-up)")
```

- [ ] **Step 2: Write `reconciler/conflicts.py`**

```python
"""Conflict draft filing — W2 implementation.

Writes wiki/ops/inbox/conflict-<run_id>.md with the conflicted files, base/
ours/theirs SHAs, and a rebase-style diff. The /inbox UI surfaces three
actions: accept-theirs, accept-ours, open-in-chat.
"""

from __future__ import annotations

from pathlib import Path

from brain_core.sandbox.types import WorktreeHandle


async def file_conflict_draft(
    handle: WorktreeHandle,
    *,
    conflicted_files: list[str],
    vault_root: Path,
) -> Path:
    raise NotImplementedError("conflict drafts are a Week 2 deliverable (ADR 0001 follow-up)")
```

- [ ] **Step 3: Commit**

```bash
git add apps/brain-core/brain_core/reconciler/three_way.py apps/brain-core/brain_core/reconciler/conflicts.py
git commit -m "feat(reconciler): stub three_way + conflicts modules with explicit NotImplementedError"
```

---

## Phase L — bench/ scaffold + baseline report + tag

### Task L1: Bench directory scaffold

**Files:**
- Create: `bench/README.md`
- Create: `bench/__init__.py`
- Create: `bench/run.py`
- Create: `bench/loadgen/__init__.py`
- Create: `bench/loadgen/profiles.py`
- Create: `bench/loadgen/generator.py`
- Create: `bench/report/__init__.py`
- Create: `bench/report/template.md.j2`
- Create: `bench/report/render.py`

- [ ] **Step 1: Write `bench/README.md`**

```markdown
# bench/

Benchmark harness for brain-v1. Produces weekly reports at `bench/reports/`.

## Run

```bash
python -m bench.run --profile sustained --concurrency 5 --duration 5m
```

## Profiles

- `ramp` — 1 → N concurrent over 5 min, hold 10 min
- `sustained` — N concurrent for the duration
- `burst` — spike/drop/spike/drop
- `mixed` — 60% chat / 20% synthesis / 15% ingest / 5% background

## Output

`bench/reports/YYYY-MM-DD-<slug>.md` with summary stats, cache hit ratio curve,
latency CDF, and top-5 slowest runs linked to Grafana Cloud traces (W3+).

## Week 1 scope

W1 ships the `sustained` profile only. The W1 baseline report exercises
submit → admission → dispatch → sandbox → reconciler end-to-end with the
fake worker to validate pipeline plumbing, not real Anthropic cost.
```

- [ ] **Step 2: Write `bench/loadgen/profiles.py`**

```python
"""Load profile definitions for bench/run.py."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Profile(enum.Enum):
    RAMP      = "ramp"
    SUSTAINED = "sustained"
    BURST     = "burst"
    MIXED     = "mixed"


@dataclass(frozen=True)
class ProfileConfig:
    profile:     Profile
    concurrency: int
    duration_sec: int


def parse_duration(s: str) -> int:
    """'5m' → 300, '30s' → 30, '1h' → 3600."""
    unit = s[-1].lower()
    value = int(s[:-1])
    return {"s": 1, "m": 60, "h": 3600}[unit] * value
```

- [ ] **Step 3: Write `bench/loadgen/generator.py`**

```python
"""Async submission generator. Hands Submitted run_ids back to the caller."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

from brain_core.scheduler import (
    AgentClass, Priority, RunSpec, TriggerSource, submit,
)


_PROMPT_FIXTURES = [
    ("smoke-a", "say hi from bench-a"),
    ("smoke-b", "say hi from bench-b"),
    ("smoke-c", "say hi from bench-c"),
]


@dataclass
class SubmissionResult:
    run_id: str
    submitted_at: float
    family: str


async def submit_one() -> SubmissionResult:
    family, prompt = random.choice(_PROMPT_FIXTURES)
    run_id = await submit(RunSpec(
        prompt=prompt,
        prompt_family=family,
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.BACKGROUND,
        trigger_source=TriggerSource.BENCH,
        payload_extra={"bench_t": time.time_ns()},
    ))
    return SubmissionResult(
        run_id=run_id,
        submitted_at=time.time(),
        family=family,
    )


async def run_sustained(concurrency: int, duration_sec: int) -> list[SubmissionResult]:
    end = time.time() + duration_sec
    results: list[SubmissionResult] = []
    in_flight: set[asyncio.Task] = set()

    while time.time() < end or in_flight:
        while time.time() < end and len(in_flight) < concurrency:
            t = asyncio.create_task(submit_one())
            in_flight.add(t)
        done, _ = await asyncio.wait(in_flight, timeout=0.5,
                                     return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            in_flight.remove(t)
            results.append(await t)

    return results
```

- [ ] **Step 4: Write `bench/run.py`**

```python
"""bench.run — CLI entrypoint.

Usage:
    python -m bench.run --profile sustained --concurrency 5 --duration 5m
"""

from __future__ import annotations

import argparse
import asyncio

from bench.loadgen.profiles import Profile, ProfileConfig, parse_duration
from bench.loadgen.generator import run_sustained
from bench.report.render import render_report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", choices=[p.value for p in Profile], required=True)
    p.add_argument("--concurrency", type=int, required=True)
    p.add_argument("--duration", required=True, help="e.g. 5m, 30s, 1h")
    p.add_argument("--out", default=None, help="output report path (default: bench/reports/<date>-<slug>.md)")
    args = p.parse_args()

    cfg = ProfileConfig(
        profile=Profile(args.profile),
        concurrency=args.concurrency,
        duration_sec=parse_duration(args.duration),
    )

    if cfg.profile != Profile.SUSTAINED:
        raise SystemExit("W1 only implements the sustained profile")

    asyncio.run(_run(cfg, args.out))


async def _run(cfg: ProfileConfig, out_path: str | None) -> None:
    results = await run_sustained(cfg.concurrency, cfg.duration_sec)
    await render_report(cfg, results, out_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Write `bench/report/template.md.j2`**

```jinja
# brain-v1 benchmark report — {{ cfg.profile.value }}

**Date:** {{ generated_at }}
**Profile:** `{{ cfg.profile.value }}`
**Concurrency:** {{ cfg.concurrency }}
**Duration:** {{ cfg.duration_sec }}s
**Commit:** `{{ commit_sha }}`

## Summary

| Metric | Value |
|---|---|
| Total submissions | {{ submissions }} |
| Runs completed | {{ completed }} |
| Runs failed | {{ failed }} |
| Success rate | {{ success_rate }}% |
| Avg end-to-end latency (ms) | {{ avg_latency_ms }} |
| P95 end-to-end latency (ms) | {{ p95_latency_ms }} |
| Prompt cache hit ratio | {{ cache_hit_ratio }}% |

## Notes

{{ notes }}
```

- [ ] **Step 6: Write `bench/report/render.py`**

```python
"""Render a benchmark markdown report.

W1 version: pulls run outcomes directly from the SQLite run_queue table (since
Grafana Cloud query integration lands in W3). Cache hit ratio is computed from
per-run cache_read_tokens / (cache_read_tokens + input_tokens).
"""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path
from statistics import mean, quantiles

import aiosqlite
from jinja2 import Template

from bench.loadgen.generator import SubmissionResult
from bench.loadgen.profiles import ProfileConfig
from brain_core import db as _db

REPORT_DIR = Path("bench/reports")


async def render_report(
    cfg: ProfileConfig,
    results: list[SubmissionResult],
    out_path: str | None,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    run_ids = [r.run_id for r in results]
    outcomes = await _fetch_outcomes(run_ids)

    completed = sum(1 for o in outcomes if o["state"] == "done")
    failed    = sum(1 for o in outcomes if o["state"] in ("failed", "conflicted"))

    latencies_ms = [
        (o["ended_at"] - o["started_at"]) * 1000
        for o in outcomes
        if o["started_at"] and o["ended_at"]
    ]
    avg_ms = round(mean(latencies_ms), 1) if latencies_ms else 0
    p95_ms = round(quantiles(latencies_ms, n=20)[18], 1) if len(latencies_ms) >= 20 else 0

    cache_ratio = 0
    total_in = sum(o.get("actual_in", 0) or 0 for o in outcomes)
    total_cache_read = sum(o.get("cache_read_tokens", 0) or 0 for o in outcomes)
    if total_in > 0:
        cache_ratio = round(100 * total_cache_read / (total_in + total_cache_read), 1)

    success_rate = round(100 * completed / max(1, len(results)), 1)

    commit_sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()

    ctx = {
        "cfg": cfg,
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "commit_sha": commit_sha,
        "submissions": len(results),
        "completed": completed,
        "failed": failed,
        "success_rate": success_rate,
        "avg_latency_ms": avg_ms,
        "p95_latency_ms": p95_ms,
        "cache_hit_ratio": cache_ratio,
        "notes": (
            "W1 baseline — fake worker (no real Anthropic calls). Validates "
            "submit → admission → dispatch → sandbox → reconciler plumbing. "
            "Cache hit ratio reflects fake worker's canned stream-json usage block."
        ),
    }

    tmpl_path = Path(__file__).parent / "template.md.j2"
    tmpl = Template(tmpl_path.read_text())
    out = Path(out_path) if out_path else (
        REPORT_DIR / f"{dt.date.today().isoformat()}-baseline.md"
    )
    out.write_text(tmpl.render(**ctx))
    print(f"wrote {out}")
    return out


async def _fetch_outcomes(run_ids: list[str]) -> list[dict]:
    if not run_ids:
        return []
    async with aiosqlite.connect(_db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(run_ids))
        cur = await conn.execute(
            f"SELECT * FROM run_queue WHERE id IN ({placeholders})",
            run_ids,
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 7: Commit**

```bash
git add bench/
git commit -m "feat(bench): scaffold harness (run.py, sustained profile, markdown report renderer)"
```

### Task L2: Run the W1 baseline benchmark

**Files:**
- Create: `bench/reports/2026-04-20-baseline.md` (generated)

- [ ] **Step 1: Ensure the fake worker image is built locally**

```bash
docker build -t brain-worker-fake:test apps/brain-core/tests/integration/fake_brain_worker
```

Expected: image built.

- [ ] **Step 2: Run the benchmark against a tmp DB + tmp vault**

```bash
cd /Users/yogeshseenichamy/second-brain
TMPDIR=$(mktemp -d)
mkdir -p "$TMPDIR"/{db,worktrees,scratch}
git clone --bare . "$TMPDIR/vault.git"
git -C "$TMPDIR/vault.git" config gc.auto 0
git -C "$TMPDIR/vault.git" worktree add "$TMPDIR/worktrees/main" main

BRAIN_DB_PATH="$TMPDIR/db/brain.sqlite" \
BRAIN_VAULT_GIT="$TMPDIR/vault.git" \
BRAIN_WORKTREE_ROOT="$TMPDIR/worktrees" \
BRAIN_SCRATCH_ROOT="$TMPDIR/scratch" \
BRAIN_WORKER_IMAGE="brain-worker-fake:test" \
uv --project apps/brain-core run python -m bench.run \
  --profile sustained --concurrency 5 --duration 5m \
  --out bench/reports/2026-04-20-baseline.md
```

Expected: 5-minute run, `bench/reports/2026-04-20-baseline.md` created. Non-zero `Total submissions`, `Runs completed` close to `Total submissions` (±a few in-flight at the deadline).

- [ ] **Step 3: Inspect the report**

```bash
cat bench/reports/2026-04-20-baseline.md
```

Look for:
- `Success rate` > 90%
- `P95 end-to-end latency (ms)` is a real number (not 0)
- `Prompt cache hit ratio` reflects the fake worker's canned values (~33%)

- [ ] **Step 4: Commit the report**

```bash
git add bench/reports/2026-04-20-baseline.md
git commit -m "bench(brain-v1): W1 baseline sustained/5/5m via fake worker"
```

### Task L3: Update modules.md with the real W1 layout and tag

**Files:**
- Modify: `docs/architecture/modules.md` — append "As of W1" section with concrete state

- [ ] **Step 1: Append to `modules.md`**

Add a new section at the bottom:

```markdown
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
| `sandbox/container.py` | done | unit (arg construction only) |
| `sandbox/exec.py` | done | unit (2) |
| `sandbox/lifecycle.py` | done | integration (via run_one) |
| `reconciler/merge.py` | done (fast-forward only) | unit (3) |
| `reconciler/three_way.py` | stub (NotImplementedError) | — |
| `reconciler/conflicts.py` | stub (NotImplementedError) | — |
| `observability/*` | not started (W1 ships without spans/metrics) | — |
| `bench/run.py` | done (sustained profile only) | manual |
| `bench/report/render.py` | done (local SQLite; Grafana query W3) | — |

### Known gaps (to resolve in W2)
- No real admission controller — cap-only stub
- No placement — FIFO over whichever container is free
- No observability emission — spans + metrics land in W2
- `main.py` still wires the legacy `agent.py` path for chat; chat-via-scheduler is a W2 task
```

- [ ] **Step 2: Commit**

```bash
git add docs/architecture/modules.md
git commit -m "docs(brain-v1): W1 module status + known gaps"
```

- [ ] **Step 3: Tag v1.0-foundations**

```bash
# Verify the tree first
git status
git log --oneline -20

git tag -a v1.0-foundations -m "Week 1 foundations — scheduler + sandbox + reconciler fast-forward + baseline bench"
git push origin v1.0-foundations
```

Expected: tag pushed; visible at `git ls-remote --tags origin | grep v1.0-foundations`.

---

## Week 1 self-review checklist (run before handing off to execution)

- [ ] Every task has complete code blocks — no "see above" placeholders
- [ ] Every method signature used in a later task is defined in an earlier task
- [ ] The state machine names (`PENDING|ADMITTED|RUNNING|RECONCILING|DONE|FAILED|CONFLICTED|INTERRUPTED`) are used consistently
- [ ] `scheduler.queue.transition_state` handles every state that tasks transition into
- [ ] `sandbox.lifecycle.execute` env vars match `sandbox.container.build_docker_run_args` env vars
- [ ] `reconciler.merge.fast_forward_or_stage` return values are `RunState`, matching what `run_one` expects
- [ ] Every ADR referenced in a task is written before it is referenced
- [ ] `v1.0-foundations` tag only fires after all unit + integration tests pass and the baseline report is committed

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-14-week-1-foundations.md`.**

This is Week 1 of 4. Weeks 2–4 will be planned at the end of each prior week, using that week's reality as the jumping-off point.

Two execution options:

**1. Subagent-Driven (recommended).** Fresh subagent per task, two-stage review between tasks. Best for the infra-heavy tasks where you want a second set of eyes verifying SSM output and terraform plans before they apply.

**2. Inline Execution.** Work tasks in this session with checkpoints. Faster for the Python/TDD phases where the edits are local and the test runs are the source of truth.

**Which approach?**

