"""run_one(Run) — the sandbox-side entry point the dispatch loop calls.

Flow:
    1. prepare_run() creates the worktree + branch
    2. start_run() launches the docker container
    3. parse_stream_json() drains stdout
    4. sandbox returns the outcome to the caller (reconciler runs next)
    5. reap_run() is called by the caller after reconcile
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from .container import start_run
from .exec import parse_stream_json
from .types import RunOutcome, WorktreeHandle
from .worktree import prepare_run, reap_run

logger = logging.getLogger(__name__)


BARE_REPO     = Path(os.environ.get("BRAIN_VAULT_GIT",  "/var/brain/vault.git"))
WORKTREE_ROOT = Path(os.environ.get("BRAIN_WORKTREE_ROOT", "/var/brain/worktrees"))
SCRATCH_ROOT  = Path(os.environ.get("BRAIN_SCRATCH_ROOT",  "/var/brain/scratch"))
WORKER_IMAGE  = os.environ.get("BRAIN_WORKER_IMAGE", "brain-worker:v1")
# Host path to the canonical Claude OAuth credentials file. Each run gets
# a per-run writable copy bind-mounted at /claude-home (see ADR 0007): the
# claude CLI needs a writable ~/.claude/ for session state AND refreshes
# OAuth tokens in-place. After a successful run, the refreshed creds are
# copied back to this canonical path so subsequent runs see the rotated
# token. The systemd claude-creds-sync.timer pushes host changes to
# Secrets Manager within 5 minutes.
CLAUDE_CREDENTIALS = Path(os.environ.get(
    "BRAIN_CLAUDE_CREDS", "/home/ubuntu/.claude/.credentials.json",
))


def _prepare_claude_home(handle: WorktreeHandle) -> Path:
    """Create a per-run writable claude-home under the run's scratch dir.

    Returns the directory path to bind-mount as /claude-home. A fresh copy
    of the host creds file is placed inside so the in-container claude CLI
    can read (and later refresh) it.
    """
    claude_home = handle.scratch_path / "claude-home"
    claude_dir = claude_home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    dst = claude_dir / ".credentials.json"
    shutil.copyfile(CLAUDE_CREDENTIALS, dst)
    # brain-core runs as uid 1000 (ubuntu) and the container also runs as
    # 1000:1000, so the default copy ownership is already correct. Tighten
    # perms so the token blob is not world-readable inside the scratch dir.
    os.chmod(dst, 0o600)
    os.chmod(claude_dir, 0o700)
    return claude_home


def _propagate_refreshed_creds(claude_home: Path) -> None:
    """If claude refreshed its token in-container, copy the new file back.

    Called only after a successful run (exit_code == 0). Atomic via os.replace
    to avoid a half-written host creds file if something crashes mid-copy.
    Best-effort: a failure here must not poison the run outcome, so the
    caller catches and logs.
    """
    src = claude_home / ".claude" / ".credentials.json"
    if not src.exists():
        return
    # Compare against the host file — if unchanged (no in-process refresh
    # happened), skip the replace to avoid needless mtime churn that would
    # trick claude-creds-sync into pushing to Secrets Manager every run.
    host = CLAUDE_CREDENTIALS
    try:
        if host.exists() and host.read_bytes() == src.read_bytes():
            return
    except OSError:
        pass
    tmp = host.with_suffix(host.suffix + ".tmp")
    shutil.copyfile(src, tmp)
    os.chmod(tmp, 0o600)
    os.replace(tmp, host)
    logger.info("claude creds refreshed by container; propagated to %s", host)


async def execute(*, run_id: str, prompt: str, prompt_family: str, model: str
                  ) -> tuple[WorktreeHandle, RunOutcome]:
    """Prepare, start, stream, return. The caller is responsible for reconcile + reap.

    Once the worktree has been created, this function ALWAYS returns the handle —
    even if the container fails to start or the stream drain blows up. Re-raising
    after prepare_run would orphan the worktree+branch in the caller. Failures
    after prepare_run are surfaced as a RunOutcome with exit_code=-1, so the
    reconciler short-circuits to FAILED and the caller still calls reap_run.
    """
    handle = await prepare_run(
        run_id=run_id,
        bare_repo=BARE_REPO,
        worktree_root=WORKTREE_ROOT,
        scratch_root=SCRATCH_ROOT,
    )

    try:
        claude_home = _prepare_claude_home(handle)
        _, stdout_iter, proc = await start_run(
            run_id=run_id,
            image=WORKER_IMAGE,
            worktree_path=handle.worktree_path,
            scratch_path=handle.scratch_path,
            bare_repo=BARE_REPO,
            claude_home=claude_home,
            prompt=prompt,
            prompt_family=prompt_family,
            model=model,
        )

        # Drain stdout and stderr concurrently. If we drain stdout-then-stderr
        # sequentially, a child that writes >64KB to stderr blocks on its pipe
        # buffer, never closes stdout, and we hang forever on the stdout iterator.
        async def _drain_stdout() -> list[bytes]:
            return [line async for line in stdout_iter]

        async def _drain_stderr() -> bytes:
            if proc.stderr is None:
                return b""
            return await proc.stderr.read()

        lines, stderr_bytes = await asyncio.gather(_drain_stdout(), _drain_stderr())
        exit_code = await proc.wait()
        stderr = stderr_bytes.decode(errors="replace")

        parsed = parse_stream_json(lines)

        if exit_code == 0:
            try:
                _propagate_refreshed_creds(claude_home)
            except Exception:
                logger.exception("failed to propagate refreshed claude creds for run_id=%s", run_id)

        outcome = RunOutcome(
            run_id=run_id,
            exit_code=exit_code,
            final_text=parsed.final_text,
            input_tokens=parsed.input_tokens,
            output_tokens=parsed.output_tokens,
            cache_read_tokens=parsed.cache_read_tokens,
            cache_write_tokens=parsed.cache_write_tokens,
            stream_events=parsed.events,
            error_detail=stderr if exit_code != 0 else None,
            error_class="docker_nonzero_exit" if exit_code != 0 else None,
        )
        return handle, outcome
    except Exception as exc:
        logger.exception("sandbox.execute failed after prepare_run for run_id=%s", run_id)
        outcome = RunOutcome(
            run_id=run_id,
            exit_code=-1,
            error_class="sandbox_exec_failed",
            error_detail=f"{type(exc).__name__}: {exc}",
        )
        return handle, outcome
