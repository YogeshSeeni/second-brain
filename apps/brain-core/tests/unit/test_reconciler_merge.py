import subprocess
from pathlib import Path

import pytest

from brain_core.reconciler.merge import fast_forward_or_stage
from brain_core.reconciler.types import ReconcileOutcome
from brain_core.sandbox.types import RunOutcome, WorktreeHandle
from brain_core.scheduler.types import RunState


def _seed_worktree_with_commit(temp_git_repo: Path, run_id: str) -> WorktreeHandle:
    bare = temp_git_repo / "vault.git"
    wt = temp_git_repo / "worktrees" / f"run-{run_id}"
    branch = f"agent/run-{run_id}"
    subprocess.run(
        ["git", "-C", str(bare), "worktree", "add", "-b", branch, str(wt), "main"],
        check=True,
    )
    (wt / f"{run_id}.md").write_text("agent wrote this\n")
    subprocess.run(
        ["git", "-C", str(wt), "-c", "user.email=a@a", "-c", "user.name=a", "add", "."],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(wt), "-c", "user.email=a@a", "-c", "user.name=a",
         "commit", "-qm", f"agent: {run_id}"],
        check=True,
    )
    return WorktreeHandle(
        run_id=run_id,
        worktree_path=wt,
        branch_name=branch,
        scratch_path=temp_git_repo / "scratch" / f"run-{run_id}",
    )


def _outcome(run_id: str, exit_code: int = 0) -> RunOutcome:
    return RunOutcome(run_id=run_id, exit_code=exit_code, final_text="ok")


@pytest.mark.asyncio
async def test_fast_forward_success_returns_done(temp_git_repo: Path):
    handle = _seed_worktree_with_commit(temp_git_repo, "ff1")
    outcome = _outcome("ff1")
    state = await fast_forward_or_stage(
        handle, outcome, bare_repo=temp_git_repo / "vault.git"
    )
    assert state == RunState.DONE

    # main now contains the new file
    main_wt = temp_git_repo / "worktrees" / "main"
    assert (main_wt / "ff1.md").exists()


@pytest.mark.asyncio
async def test_nonff_returns_conflicted_and_preserves_branch(temp_git_repo: Path):
    bare = temp_git_repo / "vault.git"
    main_wt = temp_git_repo / "worktrees" / "main"

    # Create the agent branch first (branched from current main tip)
    handle = _seed_worktree_with_commit(temp_git_repo, "nf1")
    outcome = _outcome("nf1")

    # Now advance main independently so fast-forward from agent/run-nf1 is impossible
    (main_wt / "shared.md").write_text("main version\n")
    subprocess.run(
        ["git", "-C", str(main_wt), "-c", "user.email=m@m", "-c", "user.name=m",
         "add", "."], check=True,
    )
    subprocess.run(
        ["git", "-C", str(main_wt), "-c", "user.email=m@m", "-c", "user.name=m",
         "commit", "-qm", "main divergent commit"], check=True,
    )

    state = await fast_forward_or_stage(handle, outcome, bare_repo=bare)
    assert state == RunState.CONFLICTED

    branches = subprocess.check_output(["git", "-C", str(bare), "branch"]).decode()
    assert "agent/run-nf1" in branches


@pytest.mark.asyncio
async def test_failed_outcome_does_not_merge(temp_git_repo: Path):
    handle = _seed_worktree_with_commit(temp_git_repo, "fail1")
    outcome = _outcome("fail1", exit_code=2)
    state = await fast_forward_or_stage(
        handle, outcome, bare_repo=temp_git_repo / "vault.git"
    )
    assert state == RunState.FAILED
