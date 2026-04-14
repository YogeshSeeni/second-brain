import pytest

from brain_core.scheduler import (
    AgentClass,
    Priority,
    RunSpec,
    TriggerSource,
    submit,
)
from brain_core.scheduler.queue import load_run


def _spec(**kw) -> RunSpec:
    base = dict(
        prompt="hi",
        prompt_family="test",
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.LOW,
        trigger_source=TriggerSource.JOB,
    )
    base.update(kw)
    return RunSpec(**base)


@pytest.mark.asyncio
async def test_submit_returns_run_id(temp_db: str):
    run_id = await submit(_spec())
    assert isinstance(run_id, str) and len(run_id) == 36


@pytest.mark.asyncio
async def test_submit_persists_pending_row(temp_db: str):
    run_id = await submit(_spec())
    run = await load_run(run_id)
    assert run is not None
    assert run.prompt_family == "test"


@pytest.mark.asyncio
async def test_submit_is_idempotent_for_same_payload(temp_db: str):
    spec = _spec(payload_extra={"job_name": "lc-daily", "date": "2026-04-14"})
    first = await submit(spec)
    second = await submit(spec)
    assert first == second, "same-payload submit should return the same run_id"


@pytest.mark.asyncio
async def test_submit_new_id_for_different_payload(temp_db: str):
    first = await submit(_spec(payload_extra={"date": "2026-04-14"}))
    second = await submit(_spec(payload_extra={"date": "2026-04-15"}))
    assert first != second
