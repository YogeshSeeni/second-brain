"""15-min tick routine.

Fans out to every integration the brain polls on a cadence:
  - Whoop recovery/sleep (primary today)
  - Google Calendar (Day 3+ via gcal.py; stub returns nothing for now)
  - Google Tasks    (Day 3+ via gtasks.py; stub returns nothing)

Each source can write nudges. The tick is idempotent — duplicate nudges
are deduped by (kind, source_ref) in db.create_nudge.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from . import db, whoop

logger = logging.getLogger(__name__)

LOW_RECOVERY_THRESHOLD = 40


async def _tick_whoop() -> dict[str, Any]:
    """Pull latest recovery, emit a low-recovery nudge if applicable."""
    row = await whoop.latest_recovery()
    if row is None:
        return {"ok": False, "reason": "no recovery row"}

    score = row.get("recovery_score")
    nudge_id: int | None = None
    if score is not None and score < LOW_RECOVERY_THRESHOLD:
        body = (
            f"Whoop recovery is {int(score)}% — consider lighter training "
            f"today. HRV {row.get('hrv_ms')}, RHR {row.get('resting_hr')}."
        )
        nudge_id = await db.create_nudge(
            kind="whoop",
            body=body,
            source_ref=f"whoop:{row['cycle_id']}",
        )
    return {"ok": True, "score": score, "nudge_id": nudge_id}


async def _tick_gcal() -> dict[str, Any]:
    """Stub — Day 3+ will diff gcal_seen and surface upcoming events."""
    return {"ok": True, "skipped": "gcal wired Day 3+"}


async def _tick_gtasks() -> dict[str, Any]:
    """Stub — Day 3+ will diff gtasks_seen and surface overdue tasks."""
    return {"ok": True, "skipped": "gtasks wired Day 3+"}


async def run_tick(trigger: str = "cron") -> dict[str, Any]:
    """Run every registered poller, swallow individual failures, return a
    receipt so the caller (cron or /api/tick) can log a summary."""
    ts = int(time.time())
    logger.info("tick start trigger=%s ts=%s", trigger, ts)

    results: dict[str, Any] = {"trigger": trigger, "ran_at": ts}
    for name, fn in (("whoop", _tick_whoop), ("gcal", _tick_gcal), ("gtasks", _tick_gtasks)):
        try:
            results[name] = await fn()
        except Exception as exc:  # noqa: BLE001
            logger.exception("tick %s failed: %s", name, exc)
            results[name] = {"ok": False, "error": str(exc)}

    logger.info("tick done results=%s", results)
    return results
