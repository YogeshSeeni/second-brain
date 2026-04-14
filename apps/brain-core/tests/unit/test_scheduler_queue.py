import json
import pytest

from brain_core.scheduler import (
    AgentClass,
    Priority,
    RunSpec,
    RunState,
    TriggerSource,
)
from brain_core.scheduler.queue import (
    finalize_run,
    idempotency_key_for,
    insert_run,
    list_runs_by_state,
    load_run,
    transition_state,
)


def _spec() -> RunSpec:
    return RunSpec(
        prompt="hello",
        prompt_family="lc-daily",
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.LOW,
        trigger_source=TriggerSource.JOB,
        estimated_in=1000,
        estimated_out=500,
    )


def test_idempotency_key_stable_for_same_payload():
    a = idempotency_key_for(TriggerSource.JOB, {"name": "lc-daily", "date": "2026-04-14"})
    b = idempotency_key_for(TriggerSource.JOB, {"date": "2026-04-14", "name": "lc-daily"})
    assert a == b


def test_idempotency_key_differs_for_different_payload():
    a = idempotency_key_for(TriggerSource.JOB, {"name": "lc-daily", "date": "2026-04-14"})
    b = idempotency_key_for(TriggerSource.JOB, {"name": "lc-daily", "date": "2026-04-15"})
    assert a != b


@pytest.mark.asyncio
async def test_insert_then_load(temp_db: str):
    spec = _spec()
    run_id = await insert_run(spec, idempotency_key="k1")
    run = await load_run(run_id)
    assert run is not None
    assert run.id == run_id
    assert run.state == RunState.PENDING
    assert run.priority == Priority.LOW
    assert run.agent_class == AgentClass.BACKGROUND
    assert run.prompt_family == "lc-daily"
    assert run.estimated_in == 1000
    payload = json.loads(run.payload_json)
    assert payload["prompt"] == "hello"


@pytest.mark.asyncio
async def test_transition_state_updates_timestamps(temp_db: str, fake_clock):
    spec = _spec()
    run_id = await insert_run(spec, idempotency_key="k2")
    fake_clock[0] += 5
    await transition_state(run_id, RunState.ADMITTED)
    run = await load_run(run_id)
    assert run.state == RunState.ADMITTED
    assert run.admitted_at is not None


@pytest.mark.asyncio
async def test_finalize_run_persists_outcome_fields(temp_db: str):
    import aiosqlite
    run_id = await insert_run(_spec(), idempotency_key="k-final")
    await finalize_run(
        run_id,
        RunState.FAILED,
        exit_code=1,
        error_class="docker_nonzero_exit",
        error_detail="boom",
        actual_in=42,
        actual_out=7,
    )
    async with aiosqlite.connect(temp_db) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT state, exit_code, error_class, error_detail, actual_in, actual_out, ended_at "
            "FROM run_queue WHERE id = ?",
            (run_id,),
        )
        row = await cur.fetchone()
    assert row["state"] == RunState.FAILED.value
    assert row["exit_code"] == 1
    assert row["error_class"] == "docker_nonzero_exit"
    assert row["error_detail"] == "boom"
    assert row["actual_in"] == 42
    assert row["actual_out"] == 7
    assert row["ended_at"] is not None


@pytest.mark.asyncio
async def test_finalize_run_truncates_long_error_detail(temp_db: str):
    import aiosqlite
    run_id = await insert_run(_spec(), idempotency_key="k-trunc")
    big = "x" * 10_000
    await finalize_run(run_id, RunState.FAILED, exit_code=1, error_detail=big)
    async with aiosqlite.connect(temp_db) as conn:
        cur = await conn.execute("SELECT error_detail FROM run_queue WHERE id = ?", (run_id,))
        (detail,) = await cur.fetchone()
    assert detail is not None
    assert len(detail) == 4096


@pytest.mark.asyncio
async def test_list_runs_by_state_orders_by_priority_then_created(temp_db: str, fake_clock):
    spec_low = _spec()
    spec_high = RunSpec(
        prompt="urgent",
        prompt_family="chat",
        agent_class=AgentClass.CHAT,
        priority=Priority.CRITICAL,
        trigger_source=TriggerSource.CHAT,
    )
    id_low = await insert_run(spec_low, idempotency_key="k-low")
    fake_clock[0] += 1
    id_high = await insert_run(spec_high, idempotency_key="k-high")

    pending = await list_runs_by_state(RunState.PENDING, limit=10)
    assert [r.id for r in pending] == [id_high, id_low]
