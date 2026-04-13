"""aiosqlite wrapper for threads, messages, tasks, nudges, and gcal/gtasks caches."""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("BRAIN_DB_PATH", "./db/brain.sqlite")


SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  summary_path TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL REFERENCES threads(id),
  role TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  task_id INTEGER REFERENCES agent_tasks(id)
);

CREATE TABLE IF NOT EXISTS agent_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL,
  trigger TEXT NOT NULL,
  state TEXT NOT NULL,
  pid INTEGER,
  started_at INTEGER,
  ended_at INTEGER,
  prompt_hash TEXT
);

CREATE TABLE IF NOT EXISTS thesis_state (
  axis TEXT PRIMARY KEY,
  stance TEXT NOT NULL,
  confidence REAL NOT NULL,
  last_review INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS nudges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  body TEXT NOT NULL,
  source_ref TEXT,
  created_at INTEGER NOT NULL,
  surfaced_at INTEGER,
  acknowledged_at INTEGER
);

CREATE TABLE IF NOT EXISTS gcal_seen (
  event_id TEXT PRIMARY KEY,
  etag TEXT,
  start_at INTEGER NOT NULL,
  summary TEXT,
  last_seen INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gtasks_seen (
  task_id TEXT PRIMARY KEY,
  list_id TEXT NOT NULL,
  title TEXT,
  due_at INTEGER,
  status TEXT,
  last_seen INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS job_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  trigger TEXT NOT NULL,
  started_at INTEGER NOT NULL,
  ended_at INTEGER,
  state TEXT NOT NULL,
  exit_code INTEGER,
  stdout_path TEXT,
  files_touched INTEGER
);

CREATE INDEX IF NOT EXISTS idx_job_runs_name_started
  ON job_runs (name, started_at DESC);

CREATE TABLE IF NOT EXISTS whoop_recovery (
  cycle_id TEXT PRIMARY KEY,
  start_at INTEGER NOT NULL,
  end_at INTEGER,
  recovery_score INTEGER,
  hrv_ms REAL,
  resting_hr INTEGER,
  last_seen INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS whoop_sleep (
  sleep_id TEXT PRIMARY KEY,
  start_at INTEGER NOT NULL,
  end_at INTEGER NOT NULL,
  total_ms INTEGER,
  performance_pct INTEGER,
  last_seen INTEGER NOT NULL
);
"""


def _now() -> int:
    return int(time.time())


async def init() -> None:
    """Create SQLite file (and parent dir) and apply schema if missing."""
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("db init complete at %s", DB_PATH)


async def create_thread(kind: str, title: str | None) -> str:
    """Insert a new thread row and return its id."""
    thread_id = uuid.uuid4().hex
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO threads (id, kind, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (thread_id, kind, title, now, now),
        )
        await db.commit()
    return thread_id


async def get_thread(thread_id: str) -> dict[str, Any] | None:
    """Return a thread row as a dict, or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def ensure_main_thread() -> str:
    """Return the id of the singleton main thread, creating it if missing."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id FROM threads WHERE kind = 'main' ORDER BY created_at ASC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row["id"]
    return await create_thread("main", "main")


async def list_threads() -> list[dict[str, Any]]:
    """Return all threads newest-first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM threads ORDER BY updated_at DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def insert_message(
    thread_id: str, role: str, body: str, task_id: int | None
) -> int:
    """Insert a message row and bump the thread's updated_at."""
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO messages (thread_id, role, body, created_at, task_id) VALUES (?, ?, ?, ?, ?)",
            (thread_id, role, body, now, task_id),
        )
        message_id = cur.lastrowid
        await db.execute(
            "UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id)
        )
        await db.commit()
    assert message_id is not None
    return message_id


async def list_messages(thread_id: str) -> list[dict[str, Any]]:
    """Return all messages for a thread in chronological order."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC, id ASC",
            (thread_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def create_agent_task(thread_id: str, trigger: str, prompt_hash: str) -> int:
    """Insert an agent_task in 'queued' state and return its id."""
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO agent_tasks (thread_id, trigger, state, started_at, prompt_hash) VALUES (?, ?, 'queued', ?, ?)",
            (thread_id, trigger, now, prompt_hash),
        )
        task_id = cur.lastrowid
        await db.commit()
    assert task_id is not None
    return task_id


async def set_task_state(task_id: int, state: str, pid: int | None = None) -> None:
    """Update an agent_task's state, optionally its pid, and ended_at for terminal states."""
    terminal = state in ("done", "error", "interrupted")
    async with aiosqlite.connect(DB_PATH) as db:
        if terminal:
            await db.execute(
                "UPDATE agent_tasks SET state = ?, pid = ?, ended_at = ? WHERE id = ?",
                (state, pid, _now(), task_id),
            )
        else:
            await db.execute(
                "UPDATE agent_tasks SET state = ?, pid = COALESCE(?, pid) WHERE id = ?",
                (state, pid, task_id),
            )
        await db.commit()


async def get_task(task_id: int) -> dict[str, Any] | None:
    """Return an agent_task row as a dict, or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agent_tasks WHERE id = ?", (task_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_job_run(name: str, trigger: str, stdout_path: str | None) -> int:
    """Insert a job_runs row in 'running' state and return its id."""
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO job_runs (name, trigger, started_at, state, stdout_path) "
            "VALUES (?, ?, ?, 'running', ?)",
            (name, trigger, now, stdout_path),
        )
        run_id = cur.lastrowid
        await db.commit()
    assert run_id is not None
    return run_id


async def finish_job_run(
    run_id: int,
    state: str,
    exit_code: int | None,
    files_touched: int | None,
) -> None:
    """Mark a job_runs row terminal."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE job_runs SET state = ?, exit_code = ?, files_touched = ?, ended_at = ? "
            "WHERE id = ?",
            (state, exit_code, files_touched, _now(), run_id),
        )
        await db.commit()


async def get_job_run(run_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM job_runs WHERE id = ?", (run_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def latest_job_run(name: str) -> dict[str, Any] | None:
    """Return the most recent run for a given job name, or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM job_runs WHERE name = ? ORDER BY started_at DESC LIMIT 1",
            (name,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def recent_job_runs(limit: int = 20) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM job_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def recent_agent_tasks(limit: int = 20) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM agent_tasks ORDER BY started_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def latest_whoop_recovery() -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM whoop_recovery ORDER BY start_at DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def unacked_nudges(limit: int = 10) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM nudges WHERE acknowledged_at IS NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]
