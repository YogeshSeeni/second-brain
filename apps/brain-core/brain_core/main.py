"""FastAPI app — HTTP + SSE surface for the second-brain orchestrator."""

from __future__ import annotations

import hashlib
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import agent, capture, dashboard, db, jobs, tick

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await db.init()
    yield


app = FastAPI(title="brain-core", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    thread_id: str | None = None
    body: str


class ChatResponse(BaseModel):
    task_id: int
    thread_id: str


class MessageRequest(BaseModel):
    role: str
    body: str
    task_id: int | None = None


class CaptureRequest(BaseModel):
    body: str


@app.get("/api/health")
async def health() -> dict:
    """Liveness probe."""
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
async def post_chat(req: ChatRequest) -> ChatResponse:
    """Create a thread if needed, persist the user message, and kick off an agent task."""
    thread_id = req.thread_id
    if thread_id is None:
        thread_id = await db.ensure_main_thread()
    else:
        thread = await db.get_thread(thread_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="thread not found")

    await db.insert_message(thread_id, "user", req.body, task_id=None)
    prompt_hash = hashlib.sha256(req.body.encode("utf-8")).hexdigest()
    task_id = await db.create_agent_task(thread_id, "message", prompt_hash)

    try:
        await agent.start_turn(task_id, thread_id, req.body)
    except Exception as exc:
        logger.exception("failed to start turn for task %s: %s", task_id, exc)
        await db.set_task_state(task_id, "error")
        raise HTTPException(status_code=500, detail="failed to start agent turn") from exc

    return ChatResponse(task_id=task_id, thread_id=thread_id)


@app.get("/api/chat/stream/{task_id}")
async def stream_chat(task_id: int) -> StreamingResponse:
    """SSE: tail a running task, or replay the final assistant message if already complete."""
    task = await db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    async def gen() -> AsyncIterator[bytes]:
        try:
            if task["state"] in ("done", "error", "interrupted"):
                messages = await db.list_messages(task["thread_id"])
                final = next(
                    (m for m in reversed(messages) if m.get("task_id") == task_id),
                    None,
                )
                if final:
                    yield _sse("delta", final["body"])
                yield _sse("done", "")
                return

            async for chunk in agent.subscribe(task_id):
                yield _sse(chunk.kind, chunk.data)
            yield _sse("done", "")
        except Exception as exc:
            logger.exception("stream failed for task %s: %s", task_id, exc)
            yield _sse("error", str(exc))

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(event: str, data: str) -> bytes:
    payload = data.replace("\r\n", "\n")
    lines = [f"event: {event}"]
    for line in payload.split("\n"):
        lines.append(f"data: {line}")
    lines.append("")
    lines.append("")
    return "\n".join(lines).encode("utf-8")


@app.get("/api/threads")
async def get_threads() -> list[dict]:
    """List all threads, newest-first."""
    return await db.list_threads()


@app.get("/api/threads/{thread_id}/messages")
async def get_messages(thread_id: str) -> list[dict]:
    """Return all messages on a thread in chronological order."""
    if await db.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return await db.list_messages(thread_id)


@app.post("/api/threads/{thread_id}/messages")
async def post_message(thread_id: str, req: MessageRequest) -> dict:
    """Insert a message row — used by run-job.sh --post-to-main-thread."""
    if await db.get_thread(thread_id) is None:
        raise HTTPException(status_code=404, detail="thread not found")
    message_id = await db.insert_message(thread_id, req.role, req.body, req.task_id)
    return {"message_id": message_id}


@app.post("/api/tick")
async def post_tick() -> dict:
    """Trigger the tick routine (stub for tonight)."""
    return await tick.run_tick(trigger="http")


@app.post("/api/capture")
async def post_capture(req: CaptureRequest) -> dict:
    """Classify a capture and file it into the vault."""
    if not req.body.strip():
        raise HTTPException(status_code=400, detail="empty capture")
    try:
        return await capture.capture(req.body)
    except Exception as exc:
        logger.exception("capture failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"capture failed: {exc}") from exc


@app.get("/api/jobs")
async def get_jobs() -> list[dict]:
    """List every registered job with its last run."""
    return await jobs.list_jobs()


@app.post("/api/jobs/{name}/run")
async def run_job_now(name: str) -> dict:
    """Fire a job in the background — returns the new run row immediately."""
    try:
        return await jobs.run_job(name, trigger="manual")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("run_job failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/dashboard")
async def get_dashboard() -> dict:
    """Aggregated today view for the / route."""
    return await dashboard.get_today()


@app.get("/api/nudges")
async def get_nudges(limit: int = 20) -> list[dict]:
    """List unacknowledged nudges, newest first."""
    return await db.unacked_nudges(limit)


@app.post("/api/nudges/{nudge_id}/ack")
async def ack_nudge(nudge_id: int) -> dict:
    """Mark a nudge as acknowledged."""
    ok = await db.ack_nudge(nudge_id)
    if not ok:
        raise HTTPException(status_code=404, detail="nudge not found or already acked")
    return {"ok": True, "id": nudge_id}
