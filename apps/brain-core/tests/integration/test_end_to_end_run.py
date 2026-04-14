import asyncio
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_end_to_end_run_completes(
    temp_db: str,
    temp_git_repo: Path,
    fake_worker_image: str,
    brain_runs_network: str,
):
    os.environ["BRAIN_VAULT_GIT"]      = str(temp_git_repo / "vault.git")
    os.environ["BRAIN_WORKTREE_ROOT"]  = str(temp_git_repo / "worktrees")
    os.environ["BRAIN_SCRATCH_ROOT"]   = str(temp_git_repo / "scratch")
    os.environ["BRAIN_WORKER_IMAGE"]   = fake_worker_image

    # Re-import lifecycle to pick up env-derived module-level constants
    import importlib
    from brain_core.sandbox import lifecycle
    importlib.reload(lifecycle)

    from brain_core.scheduler import (
        AgentClass, Priority, RunSpec, RunState, TriggerSource, submit,
    )
    from brain_core.scheduler.admission import run_admission_pass
    from brain_core.scheduler.dispatch import run_dispatch_pass
    from brain_core.scheduler.queue import load_run
    from brain_core.scheduler.run_one import run_one

    run_id = await submit(RunSpec(
        prompt="say hi",
        prompt_family="smoke",
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.BACKGROUND,
        trigger_source=TriggerSource.BENCH,
    ))

    await run_admission_pass(max_concurrent=5)
    await run_dispatch_pass(run_one)

    # Wait for the run_one task to finish (container start + stream + reap)
    deadline = asyncio.get_event_loop().time() + 60
    while asyncio.get_event_loop().time() < deadline:
        row = await load_run(run_id)
        if row.state in (RunState.DONE, RunState.FAILED, RunState.CONFLICTED):
            break
        await asyncio.sleep(0.5)

    row = await load_run(run_id)
    assert row.state == RunState.DONE, f"final state: {row.state}"
