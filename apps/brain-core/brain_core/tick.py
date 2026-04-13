"""15-min tick routine — STUB until Day 3.

Day 3 fans out to `gcal.list_upcoming(24)` + `gtasks.list_tasks()`, diffs
against `gcal_seen` / `gtasks_seen`, and writes nudges + optional
main-thread messages.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


async def run_tick(trigger: str = "cron") -> dict:
    """Log the tick and return a minimal receipt."""
    ts = int(time.time())
    logger.info("tick fired trigger=%s ts=%s", trigger, ts)
    return {"ok": True, "ran_at": ts}
