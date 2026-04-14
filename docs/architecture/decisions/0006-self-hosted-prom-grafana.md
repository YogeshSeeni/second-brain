# 0006 — Self-hosted Prometheus + Grafana on the brain-v1 box

**Status:** Accepted (supersedes 0003)
**Date:** 2026-04-13
**Deciders:** Yogesh Seenichamy

## Context
ADR 0003 picked Grafana Cloud free tier so the t4g.large box would not pay RAM for an observability stack. By Phase D the actual numbers came in: brain-core idles at ~280 MB, and the dispatch loop peaks at ~600 MB even under bench load. The 8 GB instance has ~6 GB unused, so the RAM argument that drove 0003 no longer binds. Meanwhile Grafana Cloud free tier requires an external account, an outbound `remote_write` path, and a credential to rotate — three moving parts whose only payoff is RAM we are not using.

## Decision
Run Prometheus 2.45.3 and Grafana 12.4.2 as two systemd units on the brain-v1 box. brain-core exposes `/metrics` as an explicit FastAPI route (not a sub-app mount, which 307-redirects and breaks Prometheus scraping). Per-service env overrides land in `/etc/brain/brain-core.env` and are pulled in via systemd `EnvironmentFile=`, so the worker image and other knobs change without editing the unit file. Metrics schema:
- `brain_runs_total{state, agent_class, trigger_source}` — counter
- `brain_run_duration_seconds{state, agent_class}` — histogram
- `brain_runs_in_flight` — gauge
- `brain_submissions_total{result}` — counter

## Alternatives considered
- **Stick with Grafana Cloud (0003).** Rejected: external account, credential rotation, and `remote_write` path for ~60 MB of saved RAM that the box does not need.
- **Datadog / Honeycomb.** Rejected for the same reasons as in 0003 — cost and lock-in.
- **VictoriaMetrics in place of Prometheus.** Rejected: Prometheus is already the interview default and the cardinality on a single-host wiki agent is trivial.

## Consequences
### Positive
- Zero external dependencies for observability — the box is self-contained
- No credential to rotate, no free-tier terms to track
- Dashboards live in the same git tree as the code that emits the metrics
- `EnvironmentFile=` pattern generalizes to future per-env knobs (API keys in Phase E)
### Negative
- Metrics and dashboards die with the instance unless backed up (mitigated: Prom data dir is on the same EBS volume that already gets snapshotted; dashboards are JSON-in-git)
- ~400 MB additional RAM (Prometheus ~250 MB, Grafana ~150 MB) — within budget
### Neutral
- Prometheus and Grafana versions are pinned in the systemd units; upgrades are a deliberate step
- ADR 0003 is superseded but kept on disk for historical context
