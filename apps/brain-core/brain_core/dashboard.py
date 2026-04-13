"""Today-dashboard aggregator — reads SQLite + wiki for the / route."""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from . import db

logger = logging.getLogger(__name__)


def _vault_root() -> Path:
    return Path(os.environ.get("BRAIN_VAULT_PATH", "/var/brain"))


def _read_priorities() -> list[str]:
    """Pull top-3 priorities from today's morning note, if one exists."""
    today = date.today().isoformat()
    path = _vault_root() / "wiki" / "ops" / f"{today}.md"
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    m = re.search(r"##\s+Priorities\s*\n(.+?)(?=\n##|\Z)", content, re.DOTALL | re.IGNORECASE)
    if not m:
        return []
    lines: list[str] = []
    for raw in m.group(1).splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        item = re.sub(r"^[\-\*\d\.\)\s]+", "", stripped).strip()
        if item:
            lines.append(item)
        if len(lines) >= 3:
            break
    return lines


def _recovery_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "score": row.get("recovery_score"),
        "hrv_ms": row.get("hrv_ms"),
        "resting_hr": row.get("resting_hr"),
        "captured_at": row.get("start_at"),
    }


def _activity_from_task(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "chat",
        "label": f"turn {row['id']} · {row.get('trigger', '?')}",
        "at": row.get("started_at") or 0,
        "state": row.get("state"),
    }


def _activity_from_job(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "job",
        "label": f"{row['name']} · {row.get('trigger', 'cron')}",
        "at": row.get("started_at") or 0,
        "state": row.get("state"),
    }


async def get_today() -> dict[str, Any]:
    """Aggregate recovery + calendar + priorities + recent activity + nudges."""
    recovery_row = await db.latest_whoop_recovery()
    tasks = await db.recent_agent_tasks(10)
    jobs = await db.recent_job_runs(10)
    nudges = await db.unacked_nudges(5)

    activity = [_activity_from_task(t) for t in tasks] + [_activity_from_job(j) for j in jobs]
    activity.sort(key=lambda a: a.get("at") or 0, reverse=True)
    activity = activity[:10]

    return {
        "recovery": _recovery_dict(recovery_row),
        "calendar": [],  # wired Day 3 via gcal.py
        "priorities": _read_priorities(),
        "recent_activity": activity,
        "nudges": [
            {
                "id": n["id"],
                "kind": n["kind"],
                "body": n["body"],
                "created_at": n["created_at"],
            }
            for n in nudges
        ],
    }
