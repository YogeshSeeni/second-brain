"""Subprocess lifecycle for `claude -p` turns, with a fan-out queue per task."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator

from . import db
from .voice import build_system_prompt

logger = logging.getLogger(__name__)

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MODEL = "claude-sonnet-4-6"

_processes: dict[int, asyncio.subprocess.Process] = {}
_queues: dict[int, asyncio.Queue[str | None]] = {}
_tasks: dict[int, asyncio.Task[None]] = {}


def _build_prompt(user_body: str, history: list[dict]) -> str:
    system = build_system_prompt()
    lines = [system, "\n\n# Conversation\n"]
    for msg in history:
        role = msg["role"]
        lines.append(f"\n## {role}\n\n{msg['body']}\n")
    lines.append(f"\n## user\n\n{user_body}\n\n## assistant\n")
    return "".join(lines)


async def _supervise(task_id: int, thread_id: str, prompt: str) -> None:
    """Spawn claude -p, stream stdout into the task queue, and persist the final reply."""
    queue = _queues[task_id]
    stderr_buf: list[bytes] = []
    stdout_buf: list[str] = []
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_BIN,
            "-p",
            prompt,
            "--model",
            CLAUDE_MODEL,
            "--output-format",
            "text",
            "--dangerously-skip-permissions",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _processes[task_id] = proc
        await db.set_task_state(task_id, "running", pid=proc.pid)

        assert proc.stdout is not None
        assert proc.stderr is not None

        async def drain_stderr() -> None:
            assert proc is not None and proc.stderr is not None
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    return
                stderr_buf.append(chunk)

        stderr_task = asyncio.create_task(drain_stderr())

        # Buffered text mode: read everything, emit once on completion.
        # Structured as a loop so a future streaming path is a drop-in replacement.
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            decoded = chunk.decode("utf-8", errors="replace")
            stdout_buf.append(decoded)

        await proc.wait()
        await stderr_task

        full = "".join(stdout_buf).strip()
        if proc.returncode == 0:
            await queue.put(full)
            await db.insert_message(thread_id, "assistant", full, task_id)
            await db.set_task_state(task_id, "done", pid=proc.pid)
        else:
            err = b"".join(stderr_buf).decode("utf-8", errors="replace").strip()
            logger.error("claude -p exited %s: %s", proc.returncode, err)
            await queue.put(f"[error] claude exited {proc.returncode}: {err}")
            await db.insert_message(
                thread_id,
                "assistant",
                f"[error] claude exited {proc.returncode}: {err}",
                task_id,
            )
            await db.set_task_state(task_id, "error", pid=proc.pid)
    except Exception as exc:
        logger.exception("supervisor crashed for task %s: %s", task_id, exc)
        try:
            await queue.put(f"[error] supervisor crash: {exc}")
            await db.insert_message(
                thread_id, "assistant", f"[error] supervisor crash: {exc}", task_id
            )
            await db.set_task_state(task_id, "error")
        except Exception:
            logger.exception("failed to persist error state for task %s", task_id)
    finally:
        await queue.put(None)
        _processes.pop(task_id, None)


async def start_turn(task_id: int, thread_id: str, user_body: str) -> None:
    """Kick off the supervisor task for a chat turn; returns immediately."""
    history = await db.list_messages(thread_id)
    # history already contains the user message we just inserted; drop the last
    # row if it matches so _build_prompt can append the user turn itself
    if history and history[-1]["role"] == "user" and history[-1]["body"] == user_body:
        history = history[:-1]
    prompt = _build_prompt(user_body, history)
    _queues[task_id] = asyncio.Queue()
    _tasks[task_id] = asyncio.create_task(_supervise(task_id, thread_id, prompt))


async def subscribe(task_id: int) -> AsyncIterator[str]:
    """Yield chunks for a running task until the supervisor posts a sentinel."""
    queue = _queues.get(task_id)
    if queue is None:
        return
    while True:
        item = await queue.get()
        if item is None:
            return
        yield item


def is_running(task_id: int) -> bool:
    """True while the supervisor task for `task_id` is still active."""
    task = _tasks.get(task_id)
    return task is not None and not task.done()


async def run_turn(
    task_id: int, thread_id: str, user_body: str
) -> AsyncIterator[str]:
    """Start a turn and stream its chunks in one call — convenience wrapper."""
    await start_turn(task_id, thread_id, user_body)
    async for chunk in subscribe(task_id):
        yield chunk
