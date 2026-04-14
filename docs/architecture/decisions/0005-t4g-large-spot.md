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
