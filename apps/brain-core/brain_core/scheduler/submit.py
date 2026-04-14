"""scheduler.submit() — the single public ingress point for agent runs.

Every caller (chat handler, tick loop, watcher, job runner, benchmark harness)
goes through this function. No subprocess spawning, no scheduling logic — just
idempotent enqueue into run_queue. The admission loop picks up from there.
"""

from __future__ import annotations

import aiosqlite

from brain_core import db as _db
from brain_core.metrics import brain_submissions_total
from .queue import idempotency_key_for, insert_run
from .types import RunSpec


async def submit(spec: RunSpec) -> str:
    """Enqueue a run. Idempotent on (trigger_source, payload_extra + prompt_family)."""
    key_payload = {"family": spec.prompt_family, **spec.payload_extra}
    key = idempotency_key_for(spec.trigger_source, key_payload)

    # Dedup against the last 24h of same-key rows.
    async with aiosqlite.connect(_db._db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT id FROM run_queue "
            "WHERE idempotency_key = ? AND created_at > strftime('%s', 'now') - 86400 "
            "ORDER BY created_at DESC LIMIT 1",
            (key,),
        )
        row = await cur.fetchone()
    if row is not None:
        return row["id"]

    brain_submissions_total.labels(
        agent_class=spec.agent_class.value,
        trigger_source=spec.trigger_source.value,
    ).inc()
    return await insert_run(spec, idempotency_key=key)
