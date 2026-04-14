"""Three-way merge path — W2 implementation (ADR 0001 follow-up).

Takes a run's branch and attempts a non-ff merge into main. On success:
(MERGED_THREEWAY, merge commit SHA). On conflict: (CONFLICTED, set of
conflicted file paths) — caller then files a conflict draft.
"""

from __future__ import annotations

from pathlib import Path

from brain_core.sandbox.types import WorktreeHandle
from .types import ReconcileOutcome


async def three_way_merge(
    handle: WorktreeHandle,
    *,
    bare_repo: Path,
) -> tuple[ReconcileOutcome, list[str]]:
    raise NotImplementedError("three-way merge is a Week 2 deliverable (ADR 0001 follow-up)")
