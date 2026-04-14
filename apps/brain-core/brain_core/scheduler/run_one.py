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

from .queue import finalize_run, load_run, transition_state
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
        except Exception as exc:
            logger.exception("sandbox.execute crashed for run_id=%s", fresh.id)
            await finalize_run(
                fresh.id,
                RunState.FAILED,
                exit_code=-1,
                error_class="sandbox_exec_crashed",
                error_detail=f"{type(exc).__name__}: {exc}",
            )
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
        except Exception as exc:
            logger.exception("reconciler crashed for run_id=%s", fresh.id)
            outcome_state = RunState.FAILED
            # Preserve any sandbox-side error but mark reconciler as the proximate cause.
            if not outcome.error_class:
                outcome.error_class = "reconciler_crashed"
                outcome.error_detail = f"{type(exc).__name__}: {exc}"

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

        await finalize_run(
            fresh.id,
            outcome_state,
            exit_code=outcome.exit_code,
            error_class=outcome.error_class,
            error_detail=outcome.error_detail,
            actual_in=outcome.input_tokens or None,
            actual_out=outcome.output_tokens or None,
            cache_read_tokens=outcome.cache_read_tokens or None,
            cache_write_tokens=outcome.cache_write_tokens or None,
        )
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
