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
