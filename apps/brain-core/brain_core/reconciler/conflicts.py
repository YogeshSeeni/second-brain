"""Conflict draft filing — W2 implementation.

Writes wiki/ops/inbox/conflict-<run_id>.md with the conflicted files, base/
ours/theirs SHAs, and a rebase-style diff. The /inbox UI surfaces three
actions: accept-theirs, accept-ours, open-in-chat.
"""

from __future__ import annotations

from pathlib import Path

from brain_core.sandbox.types import WorktreeHandle


async def file_conflict_draft(
    handle: WorktreeHandle,
    *,
    conflicted_files: list[str],
    vault_root: Path,
) -> Path:
    raise NotImplementedError("conflict drafts are a Week 2 deliverable (ADR 0001 follow-up)")
