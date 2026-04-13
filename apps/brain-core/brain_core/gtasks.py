"""Google Tasks REST wrapper — STUB until Day 3.

The stdio `gtasks` MCP is fine interactively but does NOT auto-load under
headless `claude -p`, so the backend bypasses it entirely and hits the
Google Tasks REST API (`https://tasks.googleapis.com/tasks/v1/`) directly.
OAuth refresh token is pulled from AWS Secrets Manager (`brain/google_oauth`)
at startup and exchanged for an access token per call.
"""

from __future__ import annotations

from datetime import datetime


def list_tasks(list_id: str | None = None) -> list[dict]:
    """List tasks, optionally scoped to a single list."""
    raise NotImplementedError("gtasks REST wiring lands Day 3")


def create_task(
    title: str,
    due: datetime | None = None,
    notes: str | None = None,
    list_id: str | None = None,
) -> dict:
    """Create a task on the given (or default) list."""
    raise NotImplementedError("gtasks REST wiring lands Day 3")


def complete_task(task_id: str) -> dict:
    """Mark a task complete."""
    raise NotImplementedError("gtasks REST wiring lands Day 3")


def update_task(
    task_id: str,
    title: str | None = None,
    due: datetime | None = None,
    notes: str | None = None,
) -> dict:
    """Patch fields on an existing task."""
    raise NotImplementedError("gtasks REST wiring lands Day 3")
