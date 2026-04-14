import asyncio
import pytest

from brain_core.scheduler import (
    AgentClass,
    Priority,
    RunSpec,
    RunState,
    TriggerSource,
    submit,
)
from brain_core.scheduler.admission import run_admission_pass
from brain_core.scheduler.dispatch import run_dispatch_pass
from brain_core.scheduler.queue import load_run, transition_state


@pytest.mark.asyncio
async def test_dispatch_marks_runs_running_and_calls_run_one(temp_db: str):
    await submit(RunSpec(
        prompt="x",
        prompt_family="t",
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.LOW,
        trigger_source=TriggerSource.BENCH,
    ))
    await run_admission_pass(max_concurrent=10)

    calls = []

    async def stub_run_one(run):
        calls.append(run.id)
        await transition_state(run.id, RunState.DONE)

    await run_dispatch_pass(stub_run_one)
    await asyncio.sleep(0.05)  # let the asyncio.create_task run

    assert len(calls) == 1
    final = await load_run(calls[0])
    assert final.state == RunState.DONE
