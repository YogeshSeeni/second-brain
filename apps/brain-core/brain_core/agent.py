"""Subprocess lifecycle for `claude -p` turns, with a fan-out queue per task.

Output mode: `--output-format stream-json --include-partial-messages`. Each
stdout line is a JSON envelope. We care about:

  - stream_event / content_block_start (tool_use | text)
  - stream_event / content_block_delta (text_delta)
  - result (final full text)

Thinking blocks and tool_result blocks are observed but not surfaced.
Each channel (text, tool, error, done) becomes its own SSE event type
downstream — see main.py._sse.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator

from . import db
from .voice import build_system_prompt

logger = logging.getLogger(__name__)

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MODEL = "claude-sonnet-4-6"


class StreamChunk:
    """Envelope a supervisor posts to its queue. The SSE layer translates
    each chunk into an `event:` line of the same kind."""

    __slots__ = ("kind", "data")

    def __init__(self, kind: str, data: str) -> None:
        self.kind = kind  # 'delta' | 'tool' | 'error'
        self.data = data


_processes: dict[int, asyncio.subprocess.Process] = {}
_queues: dict[int, asyncio.Queue[StreamChunk | None]] = {}
_tasks: dict[int, asyncio.Task[None]] = {}


def _build_prompt(user_body: str, history: list[dict]) -> str:
    system = build_system_prompt()
    lines = [system, "\n\n# Conversation\n"]
    for msg in history:
        role = msg["role"]
        lines.append(f"\n## {role}\n\n{msg['body']}\n")
    lines.append(f"\n## user\n\n{user_body}\n\n## assistant\n")
    return "".join(lines)


def _parse_stream_line(
    raw: str,
    block_kinds: dict[int, str],
) -> list[StreamChunk]:
    """Translate one line of `claude -p --output-format stream-json` into
    zero or more queue chunks. Tracks which content block index is text vs
    tool so text_delta chunks land in the delta channel.

    `block_kinds` is mutated as a side-effect so successive calls can see
    previously-started blocks.
    """
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return []

    t = obj.get("type")
    if t != "stream_event":
        return []

    event = obj.get("event") or {}
    et = event.get("type")

    if et == "content_block_start":
        idx = event.get("index")
        block = event.get("content_block") or {}
        bt = block.get("type")
        if isinstance(idx, int):
            block_kinds[idx] = bt or ""
        if bt == "tool_use":
            name = block.get("name") or "tool"
            payload = json.dumps({"event": "start", "name": name, "index": idx})
            return [StreamChunk("tool", payload)]
        return []

    if et == "content_block_delta":
        idx = event.get("index")
        delta = event.get("delta") or {}
        dt = delta.get("type")
        kind = block_kinds.get(idx) if isinstance(idx, int) else None
        if dt == "text_delta" and kind == "text":
            text = delta.get("text") or ""
            if text:
                return [StreamChunk("delta", text)]
        return []

    if et == "content_block_stop":
        idx = event.get("index")
        if isinstance(idx, int) and block_kinds.get(idx) == "tool_use":
            payload = json.dumps({"event": "stop", "index": idx})
            return [StreamChunk("tool", payload)]
        return []

    return []


async def _supervise(task_id: int, thread_id: str, prompt: str) -> None:
    """Spawn claude -p, parse streaming JSON, fan chunks into the queue, and
    persist the final assistant reply from the terminal `result` event."""
    queue = _queues[task_id]
    stderr_buf: list[bytes] = []
    text_buf: list[str] = []
    final_text: str | None = None
    block_kinds: dict[int, str] = {}
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_BIN,
            "-p",
            prompt,
            "--model",
            CLAUDE_MODEL,
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--dangerously-skip-permissions",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024 * 1024,
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

        while True:
            try:
                line = await proc.stdout.readline()
            except ValueError:
                # line longer than limit — claude stream-json can emit fat
                # assistant-snapshot lines when a tool input is huge. Drain
                # without parsing.
                logger.warning("stream line exceeded buffer for task %s", task_id)
                continue
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded:
                continue

            try:
                obj: dict[str, Any] = json.loads(decoded)
            except json.JSONDecodeError:
                continue

            # Terminal result carries the authoritative final text.
            # Note: subtype="success" can still have is_error=true when claude
            # ran to completion but the model call itself errored (e.g. auth).
            if obj.get("type") == "result":
                if obj.get("is_error"):
                    err = obj.get("result") or "claude returned error"
                    await queue.put(StreamChunk("error", str(err)))
                    final_text = f"[error] {err}"
                elif obj.get("subtype") == "success":
                    final_text = obj.get("result") or None
                continue

            # Everything else flows through the stream_event parser.
            for chunk in _parse_stream_line(decoded, block_kinds):
                if chunk.kind == "delta":
                    text_buf.append(chunk.data)
                await queue.put(chunk)

        await proc.wait()
        await stderr_task

        if proc.returncode == 0:
            full = (final_text or "".join(text_buf)).strip()
            if not full:
                full = "[empty reply]"
            await db.insert_message(thread_id, "assistant", full, task_id)
            await db.set_task_state(task_id, "done", pid=proc.pid)
        else:
            err = b"".join(stderr_buf).decode("utf-8", errors="replace").strip()
            logger.error("claude -p exited %s: %s", proc.returncode, err)
            body = f"[error] claude exited {proc.returncode}: {err}"
            await queue.put(StreamChunk("error", body))
            await db.insert_message(thread_id, "assistant", body, task_id)
            await db.set_task_state(task_id, "error", pid=proc.pid)
    except Exception as exc:
        logger.exception("supervisor crashed for task %s: %s", task_id, exc)
        try:
            body = f"[error] supervisor crash: {exc}"
            await queue.put(StreamChunk("error", body))
            await db.insert_message(thread_id, "assistant", body, task_id)
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


async def subscribe(task_id: int) -> AsyncIterator[StreamChunk]:
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
