"""bench.run — CLI entrypoint.

Usage:
    python -m bench.run --profile sustained --concurrency 5 --duration 5m
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
from pathlib import Path

from brain_core import db
from brain_core.sandbox.lifecycle import BARE_REPO, WORKTREE_ROOT
from brain_core.scheduler.run_one import run_one
from brain_core.scheduler.runner import start_scheduler

from bench.loadgen.profiles import Profile, ProfileConfig, parse_duration
from bench.loadgen.generator import run_sustained
from bench.report.render import render_report


def _ensure_vault_bootstrap() -> None:
    """Idempotent: bare repo at BARE_REPO with an initial commit on `main`,
    and a checked-out worktree at WORKTREE_ROOT/main. The reconciler does
    `git merge --ff-only` against that worktree, so it must exist before
    any run can land. Safe to call against an already-bootstrapped vault.
    """
    bare = Path(BARE_REPO)
    main_wt = Path(WORKTREE_ROOT) / "main"

    if not (bare / "HEAD").exists() or not (bare / "objects").exists():
        bare.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(bare)],
            check=True, capture_output=True,
        )
        # `worktree add` against a fresh bare repo fails because HEAD has no
        # commits. Seed via a temp non-bare clone: commit empty, push to bare.
        seed = bare.parent / ".bench-seed"
        import shutil
        shutil.rmtree(seed, ignore_errors=True)
        try:
            subprocess.run(
                ["git", "init", "--initial-branch=main", str(seed)],
                check=True, capture_output=True,
            )
            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@local",
                "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "bench@local",
            }
            subprocess.run(
                ["git", "-C", str(seed), "commit", "--allow-empty", "-m", "initial"],
                check=True, capture_output=True, env=env,
            )
            subprocess.run(
                ["git", "-C", str(seed), "push", str(bare), "main"],
                check=True, capture_output=True,
            )
        finally:
            shutil.rmtree(seed, ignore_errors=True)

    if not (main_wt / ".git").exists():
        main_wt.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "-C", str(bare), "worktree", "add", str(main_wt), "main"],
            check=True, capture_output=True,
        )


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
    _ensure_vault_bootstrap()
    await db.init_db()
    handle = start_scheduler(run_one)
    try:
        results = await run_sustained(cfg.concurrency, cfg.duration_sec)
    finally:
        await handle.stop()
    await render_report(cfg, results, out_path)


if __name__ == "__main__":
    main()
