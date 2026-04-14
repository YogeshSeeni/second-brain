"""Prometheus metrics for brain-v1.

Exposed at GET /metrics via prometheus_client's ASGI app, mounted in main.py.
The hooks live in scheduler.run_one (the only path every run flows through).

Naming follows the OpenMetrics convention: lowercase, snake_case, _total
suffix on counters, _seconds on duration histograms.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Total runs that reached a terminal state, labeled by outcome.
brain_runs_total = Counter(
    "brain_runs_total",
    "Total runs that reached a terminal state.",
    ["state", "agent_class", "trigger_source"],
)

# Duration from run_one entry to terminal transition (sandbox + reconcile).
# Buckets cover the realistic range for fake (~100ms) through real Anthropic
# calls (~30s) — anything slower is an outlier worth investigating.
brain_run_duration_seconds = Histogram(
    "brain_run_duration_seconds",
    "Wall-clock from run_one entry to terminal transition.",
    ["state", "agent_class"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

# Currently-executing runs (in run_one, pre-terminal). The dispatch
# concurrency cap should make this <= max_concurrent.
brain_runs_in_flight = Gauge(
    "brain_runs_in_flight",
    "Runs currently inside run_one (sandbox + reconcile in progress).",
)

# Submissions accepted by scheduler.submit() — independent of whether the
# run was admitted or executed. Diff against brain_runs_total to spot
# admission backpressure.
brain_submissions_total = Counter(
    "brain_submissions_total",
    "Runs submitted to the scheduler (pre-admission).",
    ["agent_class", "trigger_source"],
)
