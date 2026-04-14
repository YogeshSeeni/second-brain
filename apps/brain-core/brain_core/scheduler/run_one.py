"""Per-run coroutine called by dispatch for each admitted run.

This is the composition root for sandbox + reconciler. Keeping it in scheduler/
(not sandbox/) because the scheduler owns the run_queue state machine, not the
sandbox; moving the state transitions here isolates sandbox from the DB.
"""

from __future__ import annotations

import json
import logging
import time

from brain_core.metrics import (
    brain_run_duration_seconds,
    brain_runs_in_flight,
    brain_runs_total,
)
from brain_core.reconciler.merge import fast_forward_or_stage
from brain_core.sandbox import lifecycle
from brain_core.sandbox.lifecycle import BARE_REPO
from brain_core.sandbox.worktree import reap_run

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
    model  = payload.get("model", "claude-sonnet-4-5")

    agent_class = fresh.agent_class.value
    trigger_source = fresh.trigger_source.value
    started = time.monotonic()
    terminal_state: RunState = RunState.FAILED

    brain_runs_in_flight.inc()
    handle = None
    try:
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
            if handle is not None:
                try:
                    await reap_run(handle, bare_repo=BARE_REPO, delete_branch=False)
                except Exception:
                    logger.exception("reap_run cleanup failed for run_id=%s", fresh.id)
            terminal_state = RunState.FAILED
            return

        await transition_state(fresh.id, RunState.RECONCILING)

        try:
            outcome_state = await fast_forward_or_stage(handle, outcome, bare_repo=BARE_REPO)
        except Exception:
            logger.exception("reconciler crashed for run_id=%s", fresh.id)
            outcome_state = RunState.FAILED

        # Delete the branch for both DONE (merged into main) and FAILED runs.
        # Failed runs have nothing recoverable on the branch — keeping them
        # accumulates ref garbage that eventually breaks `git worktree add`
        # for new runs (we have seen 500+ leaked branches in bench loops).
        # CONFLICTED branches stay alive because they hold real staged work
        # that a human or replay loop may want to inspect.
        try:
            await reap_run(
                handle, bare_repo=BARE_REPO,
                delete_branch=(outcome_state in (RunState.DONE, RunState.FAILED)),
            )
        except Exception:
            logger.exception("reap_run failed for run_id=%s", fresh.id)

        await transition_state(fresh.id, outcome_state)
        terminal_state = outcome_state
    finally:
        brain_runs_in_flight.dec()
        elapsed = time.monotonic() - started
        state_label = terminal_state.value
        brain_runs_total.labels(
            state=state_label,
            agent_class=agent_class,
            trigger_source=trigger_source,
        ).inc()
        brain_run_duration_seconds.labels(
            state=state_label,
            agent_class=agent_class,
        ).observe(elapsed)
