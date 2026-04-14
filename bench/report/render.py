"""Render a benchmark markdown report.

W1 version: pulls run outcomes directly from the SQLite run_queue table (since
Grafana Cloud query integration lands in W3). Cache hit ratio is computed from
per-run cache_read_tokens / (cache_read_tokens + input_tokens).
"""

from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path
from statistics import mean, quantiles

import aiosqlite
from jinja2 import Template

from bench.loadgen.generator import SubmissionResult
from bench.loadgen.profiles import ProfileConfig
from brain_core import db as _db

REPORT_DIR = Path("bench/reports")


async def render_report(
    cfg: ProfileConfig,
    results: list[SubmissionResult],
    out_path: str | None,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    run_ids = [r.run_id for r in results]
    outcomes = await _fetch_outcomes(run_ids)

    completed = sum(1 for o in outcomes if o["state"] == "done")
    failed    = sum(1 for o in outcomes if o["state"] in ("failed", "conflicted"))

    latencies_ms = [
        (o["ended_at"] - o["started_at"]) * 1000
        for o in outcomes
        if o["started_at"] and o["ended_at"]
    ]
    avg_ms = round(mean(latencies_ms), 1) if latencies_ms else 0
    p95_ms = round(quantiles(latencies_ms, n=20)[18], 1) if len(latencies_ms) >= 20 else 0

    cache_ratio = 0
    total_in = sum(o.get("actual_in", 0) or 0 for o in outcomes)
    total_cache_read = sum(o.get("cache_read_tokens", 0) or 0 for o in outcomes)
    if total_in > 0:
        cache_ratio = round(100 * total_cache_read / (total_in + total_cache_read), 1)

    success_rate = round(100 * completed / max(1, len(results)), 1)

    commit_sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()

    ctx = {
        "cfg": cfg,
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "commit_sha": commit_sha,
        "submissions": len(results),
        "completed": completed,
        "failed": failed,
        "success_rate": success_rate,
        "avg_latency_ms": avg_ms,
        "p95_latency_ms": p95_ms,
        "cache_hit_ratio": cache_ratio,
        "notes": (
            "W1 baseline — fake worker (no real Anthropic calls). Validates "
            "submit → admission → dispatch → sandbox → reconciler plumbing. "
            "Cache hit ratio reflects fake worker's canned stream-json usage block."
        ),
    }

    tmpl_path = Path(__file__).parent / "template.md.j2"
    tmpl = Template(tmpl_path.read_text())
    out = Path(out_path) if out_path else (
        REPORT_DIR / f"{dt.date.today().isoformat()}-baseline.md"
    )
    out.write_text(tmpl.render(**ctx))
    print(f"wrote {out}")
    return out


async def _fetch_outcomes(run_ids: list[str]) -> list[dict]:
    if not run_ids:
        return []
    async with aiosqlite.connect(_db._db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(run_ids))
        cur = await conn.execute(
            f"SELECT * FROM run_queue WHERE id IN ({placeholders})",
            run_ids,
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
