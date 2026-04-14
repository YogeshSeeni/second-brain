from pathlib import Path
from brain_core.sandbox.container import build_docker_run_args


def test_args_include_resource_caps(tmp_path: Path):
    args = build_docker_run_args(
        run_id="r1",
        image="brain-worker:v1",
        worktree_path=tmp_path / "wt",
        scratch_path=tmp_path / "sc",
        bare_repo=tmp_path / "vault.git",
        claude_credentials=tmp_path / "creds.json",
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
        claude_credentials=tmp_path / "creds.json",
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


def test_claude_credentials_mounted_readonly_with_home_override(tmp_path: Path):
    """The worker rides on Yogesh's Claude subscription, so the host's OAuth
    credentials file is bind-mounted read-only and HOME is steered at it.
    Without this, `claude -p` inside the container would have nowhere to find
    a token and every run would fail with auth errors (ADR 0007)."""
    creds = tmp_path / "fake-creds.json"
    creds.write_text("{}")

    args = build_docker_run_args(
        run_id="r1",
        image="brain-worker:v1",
        worktree_path=tmp_path / "wt",
        scratch_path=tmp_path / "sc",
        bare_repo=tmp_path / "vault.git",
        claude_credentials=creds,
        prompt="hi",
        prompt_family="t",
        model="claude-sonnet-4-6",
        uid=1000,
        gid=1000,
    )

    # The credentials mount must be present, point at the resolved host file,
    # land at the well-known in-container path, and be read-only.
    expected = (
        f"type=bind,src={creds.resolve()},"
        f"dst=/claude-home/.claude/.credentials.json,readonly"
    )
    mount_flags = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
    assert expected in mount_flags

    # HOME must point at the mount root so `claude` finds .claude/.credentials.json.
    env_flags = [args[i + 1] for i, a in enumerate(args) if a == "-e"]
    assert "HOME=/claude-home" in env_flags
