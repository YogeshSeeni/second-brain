"""Shared pytest fixtures for brain-core unit + integration tests."""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import AsyncIterator, Iterator

import aiosqlite
import pytest


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Iterator[Path]:
    """A fresh bare git repo at tmp_path/vault.git with one initial commit
    and a long-lived worktree at tmp_path/worktrees/main."""
    bare = tmp_path / "vault.git"
    work = tmp_path / "worktrees" / "main"
    work.parent.mkdir(parents=True)

    # Seed via a scratch clone, then convert to bare
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    (seed / "README.md").write_text("seed\n")
    subprocess.run(["git", "-C", str(seed), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", "seed"],
        check=True,
    )
    subprocess.run(["git", "clone", "--bare", str(seed), str(bare)], check=True)
    subprocess.run(["git", "-C", str(bare), "config", "gc.auto", "0"], check=True)
    subprocess.run(
        ["git", "-C", str(bare), "worktree", "add", str(work), "main"],
        check=True,
    )
    yield tmp_path


@pytest.fixture
async def temp_db(tmp_path: Path) -> AsyncIterator[str]:
    """A fresh SQLite DB with the v1 schema applied."""
    db_path = tmp_path / "brain.sqlite"
    os.environ["BRAIN_DB_PATH"] = str(db_path)
    from brain_core import db  # re-imported per test

    await db.init_db()
    yield str(db_path)


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[float]]:
    """Inject a mutable monotonic clock — list[0] is the current time_ns()/1e9."""
    now = [1_700_000_000.0]
    monkeypatch.setattr("time.time", lambda: now[0])
    monkeypatch.setattr("time.monotonic", lambda: now[0])
    yield now
