import asyncio
import pytest
from pathlib import Path

from brain_core.sandbox import WorktreeHandle, lifecycle
from brain_core.sandbox.worktree import prepare_run, reap_run


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


@pytest.mark.asyncio
async def test_execute_returns_handle_when_start_run_raises(
    temp_git_repo: Path, monkeypatch: pytest.MonkeyPatch,
):
    """Regression: if start_run raises after prepare_run created the worktree,
    execute() must still return the handle so the caller can reap. Re-raising
    leaks the worktree+branch (we have seen 500+ leaked branches in bench loops)."""
    monkeypatch.setattr(lifecycle, "BARE_REPO", temp_git_repo / "vault.git")
    monkeypatch.setattr(lifecycle, "WORKTREE_ROOT", temp_git_repo / "worktrees")
    monkeypatch.setattr(lifecycle, "SCRATCH_ROOT", temp_git_repo / "scratch")

    async def boom(**_kwargs):
        raise RuntimeError("docker daemon not reachable")

    monkeypatch.setattr(lifecycle, "start_run", boom)

    handle, outcome = await lifecycle.execute(
        run_id="leak-canary",
        prompt="hi",
        prompt_family="smoke",
        model="claude-sonnet-4-5",
    )
    assert handle is not None
    assert handle.branch_name == "agent/run-leak-canary"
    assert handle.worktree_path.exists()
    assert outcome.exit_code == -1
    assert outcome.error_class == "sandbox_exec_failed"
    assert "docker daemon" in (outcome.error_detail or "")

    # Caller can now reap cleanly — the whole point of the fix.
    await reap_run(handle, bare_repo=temp_git_repo / "vault.git", delete_branch=True)
    assert not handle.worktree_path.exists()
    import subprocess as sp
    branches = sp.check_output(
        ["git", "-C", str(temp_git_repo / "vault.git"), "branch"]
    ).decode()
    assert "agent/run-leak-canary" not in branches
