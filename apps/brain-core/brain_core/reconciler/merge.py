"""Fast-forward reconciler for W1.

Three-way merge and conflict-draft filing land in W2 (ADR 0001 follow-up).
For W1: if the run produced a non-zero exit code → FAILED. Else try
fast-forward. Success → DONE. Non-ff → CONFLICTED (branch preserved for
the W2 three-way path or manual resolution).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from brain_core.sandbox.types import RunOutcome, WorktreeHandle
from brain_core.scheduler.types import RunState

logger = logging.getLogger(__name__)


async def fast_forward_or_stage(
    handle: WorktreeHandle,
    outcome: RunOutcome,
    *,
    bare_repo: Path,
) -> RunState:
    if outcome.exit_code != 0:
        logger.info("reconciler: run %s failed (exit=%s) — skipping merge",
                    handle.run_id, outcome.exit_code)
        return RunState.FAILED

    main_worktree = bare_repo.parent / "worktrees" / "main"

    try:
        await _git(main_worktree, "merge", "--ff-only", handle.branch_name)
    except RuntimeError as err:
        logger.info("reconciler: fast-forward failed for %s — %s",
                    handle.run_id, err)
        return RunState.CONFLICTED

    logger.info("reconciler: fast-forward succeeded for %s", handle.run_id)
    return RunState.DONE


async def _git(cwd: Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(cwd), *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({proc.returncode}): {stderr.decode()}"
        )
    return stdout.decode()
