import aiosqlite
import pytest

from brain_core import db


@pytest.mark.asyncio
async def test_run_queue_migration_applied(temp_db: str):
    async with aiosqlite.connect(temp_db) as conn:
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='run_queue'"
        )
        row = await cur.fetchone()
    assert row is not None, "run_queue table missing after init_db()"


@pytest.mark.asyncio
async def test_migrations_idempotent(temp_db: str):
    # Re-running migrations must not throw
    await db.run_migrations()
    await db.run_migrations()

    async with aiosqlite.connect(temp_db) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=2")
        (count,) = await cur.fetchone()
    assert count == 1
