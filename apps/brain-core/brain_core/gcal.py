"""Google Calendar adapter — STUB until Day 3.

Strategy: the backend proxies to the hosted Claude.ai Google Calendar MCP
connectors (tool names prefixed `mcp__claude_ai_Google_Calendar__*`). Those
tools work in `claude -p` unlike stdio MCP servers, so we surface them via
thin helpers here. Draft invites to external attendees write to
`wiki/ops/inbox/` instead of calling `gcal_create_event` directly — see the
autonomy boundary in the plan.
"""

from __future__ import annotations

from datetime import datetime


def list_upcoming(horizon_hours: int) -> list[dict]:
    """Return events in the next `horizon_hours`."""
    raise NotImplementedError("gcal wiring lands Day 3")


def find_free_time(
    duration_min: int, window_start: datetime, window_end: datetime
) -> list[tuple[datetime, datetime]]:
    """Return free (start, end) slots of at least `duration_min` in the window."""
    raise NotImplementedError("gcal wiring lands Day 3")


def create_event(
    summary: str,
    start: datetime,
    end: datetime,
    description: str | None = None,
    attendees: list[str] | None = None,
) -> dict:
    """Create an event on the owner's primary calendar."""
    raise NotImplementedError("gcal wiring lands Day 3")


def draft_invite(
    summary: str,
    start: datetime,
    end: datetime,
    attendees: list[str],
    description: str | None = None,
) -> str:
    """Write a draft invite to wiki/ops/inbox/ and return its path."""
    raise NotImplementedError("gcal wiring lands Day 3")
