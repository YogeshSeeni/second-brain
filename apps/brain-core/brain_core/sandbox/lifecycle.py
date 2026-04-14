"""run_one(Run) — the sandbox-side entry point the dispatch loop calls.

Flow:
    1. prepare_run() creates the worktree + branch
    2. start_run() launches the docker container
    3. parse_stream_json() drains stdout
    4. sandbox returns the outcome to the caller (reconciler runs next)
    5. reap_run() is called by the caller after reconcile
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .container import start_run
from .exec import parse_stream_json
from .types import RunOutcome, WorktreeHandle
from .worktree import prepare_run, reap_run

logger = logging.getLogger(__name__)


BARE_REPO     = Path(os.environ.get("BRAIN_VAULT_GIT",  "/var/brain/vault.git"))
WORKTREE_ROOT = Path(os.environ.get("BRAIN_WORKTREE_ROOT", "/var/brain/worktrees"))
SCRATCH_ROOT  = Path(os.environ.get("BRAIN_SCRATCH_ROOT",  "/var/brain/scratch"))
WORKER_IMAGE  = os.environ.get("BRAIN_WORKER_IMAGE", "brain-worker:v1")


async def execute(*, run_id: str, prompt: str, prompt_family: str, model: str
                  ) -> tuple[WorktreeHandle, RunOutcome]:
    """Prepare, start, stream, return. The caller is responsible for reconcile + reap."""
    handle = await prepare_run(
        run_id=run_id,
        bare_repo=BARE_REPO,
        worktree_root=WORKTREE_ROOT,
        scratch_root=SCRATCH_ROOT,
    )

    _, stdout_iter, proc = await start_run(
        run_id=run_id,
        image=WORKER_IMAGE,
        worktree_path=handle.worktree_path,
        scratch_path=handle.scratch_path,
        prompt=prompt,
        prompt_family=prompt_family,
        model=model,
    )

    lines: list[bytes] = []
    async for line in stdout_iter:
        lines.append(line)

    exit_code = await proc.wait()
    stderr = (await proc.stderr.read()).decode() if proc.stderr else ""

    parsed = parse_stream_json(lines)

    outcome = RunOutcome(
        run_id=run_id,
        exit_code=exit_code,
        final_text=parsed.final_text,
        input_tokens=parsed.input_tokens,
        output_tokens=parsed.output_tokens,
        cache_read_tokens=parsed.cache_read_tokens,
        cache_write_tokens=parsed.cache_write_tokens,
        stream_events=parsed.events,
        error_detail=stderr if exit_code != 0 else None,
        error_class="docker_nonzero_exit" if exit_code != 0 else None,
    )
    return handle, outcome
