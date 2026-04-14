"""Public types for brain_core.sandbox."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class WorktreeHandle:
    run_id: str
    worktree_path: Path
    branch_name: str
    scratch_path: Path


@dataclass(frozen=True)
class ContainerHandle:
    run_id: str
    container_id: str  # docker container id (12+ chars)


@dataclass
class RunOutcome:
    run_id: str
    exit_code: int
    final_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    stream_events: list[dict] = field(default_factory=list)
    error_class: str | None = None
    error_detail: str | None = None
