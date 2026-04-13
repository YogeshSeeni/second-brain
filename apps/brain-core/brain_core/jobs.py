"""Named job registry + runner — wraps .scripts/run-job.sh."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from . import db

logger = logging.getLogger(__name__)


def _vault_root() -> Path:
    return Path(os.environ.get("BRAIN_VAULT_PATH", "/var/brain"))


# Name → crontab cadence (string for display only). Source of truth is
# .scripts/cron/crontab.template; this mirror is for the /jobs UI.
SCHEDULES: dict[str, str | None] = {
    "morning": "daily 07:30",
    "evening": "daily 22:00",
    "whoop-pull": "daily 06:00",
    "arxiv-digest": "daily 06:00",
    "lc-daily": "daily 08:00",
    "canvas-sync": "weekdays 07:00",
    "weekly-review": "sun 09:00",
    "lint": "sun 09:30",
    "recruiting-prep": "sun 10:00",
    "thesis-review": "sun 11:00",
}


def registered_jobs() -> list[str]:
    """Return job names that have a jobs/<name>.md prompt file."""
    root = _vault_root() / "jobs"
    if not root.exists():
        return []
    names = sorted(p.stem for p in root.glob("*.md"))
    return names


async def list_jobs() -> list[dict[str, Any]]:
    """Return one entry per registered job, with its last run."""
    out: list[dict[str, Any]] = []
    for name in registered_jobs():
        last = await db.latest_job_run(name)
        out.append(
            {
                "name": name,
                "schedule": SCHEDULES.get(name),
                "last_run": last,
            }
        )
    return out


async def run_job(name: str, trigger: str = "manual") -> dict[str, Any]:
    """Fire `.scripts/run-job.sh --job <name>` in the background, return the run row."""
    root = _vault_root()
    job_file = root / "jobs" / f"{name}.md"
    if not job_file.exists():
        raise FileNotFoundError(f"jobs/{name}.md not found under {root}")

    script = root / ".scripts" / "run-job.sh"
    if not script.exists():
        raise FileNotFoundError(f"run-job.sh not found at {script}")

    log_dir = root / ".scripts" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    stdout_path = str(log_dir / f"{name}-{ts}.log")

    run_id = await db.create_job_run(name, trigger, stdout_path)
    asyncio.create_task(_supervise(run_id, name, str(script)))
    row = await db.get_job_run(run_id)
    assert row is not None
    return row


async def _supervise(run_id: int, name: str, script: str) -> None:
    """Run the subprocess and update the row on exit."""
    try:
        proc = await asyncio.create_subprocess_exec(
            script,
            "--job",
            name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await proc.wait()
        state = "done" if rc == 0 else "error"
        await db.finish_job_run(run_id, state, rc, files_touched=None)
        logger.info("job %s run %s finished rc=%s", name, run_id, rc)
    except Exception as exc:
        logger.exception("job %s run %s crashed: %s", name, run_id, exc)
        try:
            await db.finish_job_run(run_id, "error", None, files_touched=None)
        except Exception:
            logger.exception("failed to mark run %s error", run_id)
