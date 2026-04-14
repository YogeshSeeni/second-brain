from pathlib import Path
from brain_core.sandbox.container import build_docker_run_args


def test_args_include_resource_caps(tmp_path: Path):
    args = build_docker_run_args(
        run_id="r1",
        image="brain-worker:v1",
        worktree_path=tmp_path / "wt",
        scratch_path=tmp_path / "sc",
        bare_repo=tmp_path / "vault.git",
        claude_home=tmp_path / "claude-home",
        prompt="hi",
        prompt_family="t",
        model="claude-sonnet-4-6",
        uid=1000,
        gid=1000,
    )
    joined = " ".join(args)
    assert "--cpus=1.0" in joined
    assert "--memory=512m" in joined
    assert "--pids-limit=256" in joined
    assert "--network=brain-runs" in joined
    assert "--security-opt no-new-privileges" in joined
    assert "--cap-drop=ALL" in joined
    assert "--user 1000:1000" in joined
    assert str(tmp_path / "wt") in joined
    assert "BRAIN_RUN_ID=r1" in joined
    assert "BRAIN_PROMPT_FAMILY=t" in joined
    assert "brain-worker:v1" in joined


def test_args_envvars_are_individual_flags(tmp_path: Path):
    args = build_docker_run_args(
        run_id="r1",
        image="brain-worker:v1",
        worktree_path=tmp_path / "wt",
        scratch_path=tmp_path / "sc",
        bare_repo=tmp_path / "vault.git",
        claude_home=tmp_path / "claude-home",
        prompt="hi",
        prompt_family="t",
        model="claude-sonnet-4-6",
        uid=1000,
        gid=1000,
    )
    # Each env var is passed as two args: "-e", "KEY=VALUE"
    env_flags = [i for i, a in enumerate(args) if a == "-e"]
    env_vars = [args[i + 1] for i in env_flags]
    assert any(v.startswith("BRAIN_RUN_ID=") for v in env_vars)
    assert any(v.startswith("BRAIN_PROMPT=") for v in env_vars)


def test_claude_home_mounted_rw_with_home_override(tmp_path: Path):
    """The worker rides on Yogesh's Claude subscription, so a per-run writable
    claude-home is bind-mounted at /claude-home and HOME is steered at it.
    The claude CLI needs a writable ~/.claude/ for session state and refreshes
    OAuth tokens in-place; a read-only single-file mount would hang the CLI
    silently on its first write (see ADR 0007, revised)."""
    home = tmp_path / "claude-home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text("{}")

    args = build_docker_run_args(
        run_id="r1",
        image="brain-worker:v1",
        worktree_path=tmp_path / "wt",
        scratch_path=tmp_path / "sc",
        bare_repo=tmp_path / "vault.git",
        claude_home=home,
        prompt="hi",
        prompt_family="t",
        model="claude-sonnet-4-6",
        uid=1000,
        gid=1000,
    )

    # The claude-home mount must be present, point at the resolved host dir,
    # land at /claude-home, and NOT be read-only (tokens are refreshed in-place).
    expected = f"type=bind,src={home.resolve()},dst=/claude-home"
    mount_flags = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
    assert expected in mount_flags
    assert not any("readonly" in m and "/claude-home" in m for m in mount_flags)

    # HOME must point at the mount root so `claude` finds .claude/.credentials.json.
    env_flags = [args[i + 1] for i, a in enumerate(args) if a == "-e"]
    assert "HOME=/claude-home" in env_flags
