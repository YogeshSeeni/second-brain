# 0003 — Grafana Cloud free tier vs local Prometheus/Tempo/Grafana

**Status:** Superseded-by-0006
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
