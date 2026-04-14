"""aiosqlite helpers for the run_queue table.

All writes go through this module; nothing else touches the raw SQL. Keeps the
SQL localized and makes it easy to add instrumentation later.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

import aiosqlite

from brain_core import db as _db
from .types import (
    AgentClass,
    Priority,
    Run,
    RunSpec,
    RunState,
    TriggerSource,
)


def idempotency_key_for(source: TriggerSource, payload: dict[str, Any]) -> str:
    """Stable hash over (trigger source, canonicalized payload).

    Payload is canonicalized via json.dumps(..., sort_keys=True) so that
    semantically identical dicts produce identical keys regardless of key order.
    """
    h = hashlib.sha256()
    h.update(source.value.encode())
    h.update(b"|")
    h.update(json.dumps(payload, sort_keys=True, default=str).encode())
    return h.hexdigest()[:32]


async def insert_run(spec: RunSpec, *, idempotency_key: str) -> str:
    run_id = str(uuid.uuid4())
    now = int(time.time())
    payload = {
        "prompt": spec.prompt,
        "model": spec.model,
        "vault_scope": list(spec.vault_scope),
        **spec.payload_extra,
    }
    async with aiosqlite.connect(_db._db_path()) as conn:
        await conn.execute(
            """
            INSERT INTO run_queue (
                id, idempotency_key, state, priority, agent_class,
                trigger_source, prompt_family, payload_json,
                estimated_in, estimated_out, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                idempotency_key,
                RunState.PENDING.value,
                int(spec.priority),
                spec.agent_class.value,
                spec.trigger_source.value,
                spec.prompt_family,
                json.dumps(payload),
                spec.estimated_in,
                spec.estimated_out,
                now,
            ),
        )
        await conn.commit()
    return run_id


async def load_run(run_id: str) -> Run | None:
    async with aiosqlite.connect(_db._db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM run_queue WHERE id = ?", (run_id,))
        row = await cur.fetchone()
    return _row_to_run(row) if row else None


async def transition_state(run_id: str, new_state: RunState) -> None:
    now = int(time.time())
    ts_col = {
        RunState.ADMITTED:    "admitted_at",
        RunState.RUNNING:     "started_at",
        RunState.DONE:        "ended_at",
        RunState.FAILED:      "ended_at",
        RunState.CONFLICTED:  "ended_at",
        RunState.INTERRUPTED: "ended_at",
    }.get(new_state)

    async with aiosqlite.connect(_db._db_path()) as conn:
        if ts_col:
            await conn.execute(
                f"UPDATE run_queue SET state = ?, {ts_col} = COALESCE({ts_col}, ?) WHERE id = ?",
                (new_state.value, now, run_id),
            )
        else:
            await conn.execute(
                "UPDATE run_queue SET state = ? WHERE id = ?",
                (new_state.value, run_id),
            )
        await conn.commit()


async def list_runs_by_state(state: RunState, *, limit: int = 50) -> list[Run]:
    async with aiosqlite.connect(_db._db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM run_queue WHERE state = ? "
            "ORDER BY priority ASC, created_at ASC LIMIT ?",
            (state.value, limit),
        )
        rows = await cur.fetchall()
    return [_row_to_run(r) for r in rows]


def _row_to_run(row: aiosqlite.Row) -> Run:
    return Run(
        id=row["id"],
        idempotency_key=row["idempotency_key"],
        state=RunState(row["state"]),
        priority=Priority(row["priority"]),
        agent_class=AgentClass(row["agent_class"]),
        trigger_source=TriggerSource(row["trigger_source"]),
        prompt_family=row["prompt_family"],
        payload_json=row["payload_json"],
        estimated_in=row["estimated_in"],
        estimated_out=row["estimated_out"],
        created_at=row["created_at"],
        admitted_at=row["admitted_at"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
    )
