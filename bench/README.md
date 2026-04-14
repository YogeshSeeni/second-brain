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
