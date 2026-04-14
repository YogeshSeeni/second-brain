"""bench.run — CLI entrypoint.

Usage:
    python -m bench.run --profile sustained --concurrency 5 --duration 5m
"""

from __future__ import annotations

import argparse
import asyncio

from brain_core import db
from brain_core.scheduler.run_one import run_one
from brain_core.scheduler.runner import start_scheduler

from bench.loadgen.profiles import Profile, ProfileConfig, parse_duration
from bench.loadgen.generator import run_sustained
from bench.report.render import render_report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", choices=[p.value for p in Profile], required=True)
    p.add_argument("--concurrency", type=int, required=True)
    p.add_argument("--duration", required=True, help="e.g. 5m, 30s, 1h")
    p.add_argument("--out", default=None, help="output report path (default: bench/reports/<date>-<slug>.md)")
    args = p.parse_args()

    cfg = ProfileConfig(
        profile=Profile(args.profile),
        concurrency=args.concurrency,
        duration_sec=parse_duration(args.duration),
    )

    if cfg.profile != Profile.SUSTAINED:
        raise SystemExit("W1 only implements the sustained profile")

    asyncio.run(_run(cfg, args.out))


async def _run(cfg: ProfileConfig, out_path: str | None) -> None:
    await db.init_db()
    handle = start_scheduler(run_one)
    try:
        results = await run_sustained(cfg.concurrency, cfg.duration_sec)
    finally:
        await handle.stop()
    await render_report(cfg, results, out_path)


if __name__ == "__main__":
    main()
