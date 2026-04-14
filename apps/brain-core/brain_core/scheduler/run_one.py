"""Per-run coroutine called by dispatch for each admitted run.

This is the composition root for sandbox + reconciler. Keeping it in scheduler/
(not sandbox/) because the scheduler owns the run_queue state machine, not the
sandbox; moving the state transitions here isolates sandbox from the DB.
"""

from __future__ import annotations

import json
import logging

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

    handle = None
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
        # If prepare_run succeeded but a later step raised, the worktree is
        # orphaned. Reap it but keep the branch — the W2 three-way path or
        # manual recovery may want to inspect it.
        if handle is not None:
            try:
                await reap_run(handle, bare_repo=BARE_REPO, delete_branch=False)
            except Exception:
                logger.exception("reap_run cleanup failed for run_id=%s", fresh.id)
        return

    await transition_state(fresh.id, RunState.RECONCILING)

    try:
        outcome_state = await fast_forward_or_stage(handle, outcome, bare_repo=BARE_REPO)
    except Exception:
        logger.exception("reconciler crashed for run_id=%s", fresh.id)
        outcome_state = RunState.FAILED

    try:
        await reap_run(handle, bare_repo=BARE_REPO,
                       delete_branch=(outcome_state == RunState.DONE))
    except Exception:
        logger.exception("reap_run failed for run_id=%s", fresh.id)

    await transition_state(fresh.id, outcome_state)
