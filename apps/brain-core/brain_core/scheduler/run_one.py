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
