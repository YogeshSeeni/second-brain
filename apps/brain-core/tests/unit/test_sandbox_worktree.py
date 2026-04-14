import asyncio
import pytest
from pathlib import Path

from brain_core.sandbox.worktree import prepare_run, reap_run
from brain_core.sandbox import WorktreeHandle


@pytest.mark.asyncio
async def test_prepare_run_creates_worktree_and_branch(temp_git_repo: Path):
    bare = temp_git_repo / "vault.git"
    handle = await prepare_run(
        run_id="abc123",
        bare_repo=bare,
        worktree_root=temp_git_repo / "worktrees",
        scratch_root=temp_git_repo / "scratch",
    )
    assert isinstance(handle, WorktreeHandle)
    assert handle.worktree_path.exists()
    assert (handle.worktree_path / "README.md").exists()
    assert handle.branch_name == "agent/run-abc123"
    assert handle.scratch_path.exists()


@pytest.mark.asyncio
async def test_reap_run_removes_worktree_and_keeps_branch(temp_git_repo: Path):
    bare = temp_git_repo / "vault.git"
    handle = await prepare_run(
        run_id="r1",
        bare_repo=bare,
        worktree_root=temp_git_repo / "worktrees",
        scratch_root=temp_git_repo / "scratch",
    )
    # Simulate an agent writing a file and committing
    (handle.worktree_path / "new.md").write_text("hello\n")
    import subprocess as sp
    sp.run(["git", "-C", str(handle.worktree_path),
            "-c", "user.email=a@a", "-c", "user.name=a",
            "add", "."], check=True)
    sp.run(["git", "-C", str(handle.worktree_path),
            "-c", "user.email=a@a", "-c", "user.name=a",
            "commit", "-qm", "agent: r1"], check=True)

    await reap_run(handle, bare_repo=bare, delete_branch=False)
    assert not handle.worktree_path.exists()
    # Branch preserved for the reconciler in the fail path
    branches = sp.check_output(["git", "-C", str(bare), "branch"]).decode()
    assert "agent/run-r1" in branches


@pytest.mark.asyncio
async def test_reap_run_deletes_branch_when_requested(temp_git_repo: Path):
    bare = temp_git_repo / "vault.git"
    handle = await prepare_run(
        run_id="r2",
        bare_repo=bare,
        worktree_root=temp_git_repo / "worktrees",
        scratch_root=temp_git_repo / "scratch",
    )
    await reap_run(handle, bare_repo=bare, delete_branch=True)
    import subprocess as sp
    branches = sp.check_output(["git", "-C", str(bare), "branch"]).decode()
    assert "agent/run-r2" not in branches
