"""brain_core.sandbox — per-run isolation via git worktree + docker container."""

from .types import WorktreeHandle, ContainerHandle, RunOutcome

__all__ = ["WorktreeHandle", "ContainerHandle", "RunOutcome"]
