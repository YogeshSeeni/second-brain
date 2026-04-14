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
