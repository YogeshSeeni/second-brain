"""Git-worktree lifecycle for one run.

prepare_run() creates /var/brain/worktrees/run-<id>/ on a fresh branch
agent/run-<id>, branched from main. reap_run() removes the worktree and
optionally deletes the branch (merged runs delete; failed/conflicted runs
keep the branch alive for the reconciler).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .types import WorktreeHandle


async def prepare_run(
    *,
    run_id: str,
    bare_repo: Path,
    worktree_root: Path,
    scratch_root: Path,
) -> WorktreeHandle:
    worktree_path = worktree_root / f"run-{run_id}"
    scratch_path  = scratch_root  / f"run-{run_id}"
    branch_name   = f"agent/run-{run_id}"

    scratch_path.mkdir(parents=True, exist_ok=True)

    await _git(bare_repo,
        "worktree", "add", "-b", branch_name, str(worktree_path), "main")

    return WorktreeHandle(
        run_id=run_id,
        worktree_path=worktree_path,
        branch_name=branch_name,
        scratch_path=scratch_path,
    )


async def reap_run(
    handle: WorktreeHandle,
    *,
    bare_repo: Path,
    delete_branch: bool,
) -> None:
    # Force is required because uncommitted changes in the worktree are
    # recoverable via the branch; the worktree directory itself is disposable.
    await _git(bare_repo, "worktree", "remove", "--force", str(handle.worktree_path))
    if delete_branch:
        await _git(bare_repo, "branch", "-D", handle.branch_name)

    # Clean up scratch (best-effort)
    import shutil
    shutil.rmtree(handle.scratch_path, ignore_errors=True)


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
