import pytest

from brain_core.scheduler import (
    AgentClass,
    Priority,
    RunSpec,
    RunState,
    TriggerSource,
    submit,
)
from brain_core.scheduler.queue import list_runs_by_state
from brain_core.scheduler.admission import run_admission_pass


def _spec(family: str) -> RunSpec:
    return RunSpec(
        prompt=f"hi {family}",
        prompt_family=family,
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.NORMAL,
        trigger_source=TriggerSource.BENCH,
        payload_extra={"family": family},
    )


@pytest.mark.asyncio
async def test_admission_promotes_pending_up_to_cap(temp_db: str):
    for i in range(12):
        await submit(_spec(f"fam-{i}"))
    admitted = await run_admission_pass(max_concurrent=10)
    assert admitted == 10  # capped

    admitted_rows = await list_runs_by_state(RunState.ADMITTED)
    pending_rows = await list_runs_by_state(RunState.PENDING)
    assert len(admitted_rows) == 10
    assert len(pending_rows) == 2


@pytest.mark.asyncio
async def test_admission_respects_existing_admitted(temp_db: str):
    for i in range(3):
        await submit(_spec(f"fam-{i}"))
    await run_admission_pass(max_concurrent=10)
    for i in range(10):
        await submit(_spec(f"fam2-{i}"))
    admitted = await run_admission_pass(max_concurrent=10)
    assert admitted == 7  # 3 already admitted, 7 free slots


@pytest.mark.asyncio
async def test_admission_orders_by_priority(temp_db: str):
    await submit(RunSpec(
        prompt="low", prompt_family="low",
        agent_class=AgentClass.BACKGROUND, priority=Priority.LOW,
        trigger_source=TriggerSource.BENCH, payload_extra={"x": "low"},
    ))
    await submit(RunSpec(
        prompt="crit", prompt_family="crit",
        agent_class=AgentClass.CHAT, priority=Priority.CRITICAL,
        trigger_source=TriggerSource.CHAT, payload_extra={"x": "crit"},
    ))
    await run_admission_pass(max_concurrent=1)
    admitted_rows = await list_runs_by_state(RunState.ADMITTED)
    assert len(admitted_rows) == 1
    assert admitted_rows[0].prompt_family == "crit"
