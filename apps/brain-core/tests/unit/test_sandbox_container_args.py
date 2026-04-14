from pathlib import Path
from brain_core.sandbox.container import build_docker_run_args


def test_args_include_resource_caps(tmp_path: Path):
    args = build_docker_run_args(
        run_id="r1",
        image="brain-worker:v1",
        worktree_path=tmp_path / "wt",
        scratch_path=tmp_path / "sc",
        prompt="hi",
        prompt_family="t",
        model="claude-sonnet-4-6",
    )
    joined = " ".join(args)
    assert "--cpus=1.0" in joined
    assert "--memory=512m" in joined
    assert "--pids-limit=256" in joined
    assert "--network=brain-runs" in joined
    assert "--security-opt no-new-privileges" in joined
    assert "--cap-drop=ALL" in joined
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
        prompt="hi",
        prompt_family="t",
        model="claude-sonnet-4-6",
    )
    # Each env var is passed as two args: "-e", "KEY=VALUE"
    env_flags = [i for i, a in enumerate(args) if a == "-e"]
    env_vars = [args[i + 1] for i in env_flags]
    assert any(v.startswith("BRAIN_RUN_ID=") for v in env_vars)
    assert any(v.startswith("BRAIN_PROMPT=") for v in env_vars)
