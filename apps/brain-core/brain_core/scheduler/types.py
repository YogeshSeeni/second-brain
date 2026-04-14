"""Public types for brain_core.scheduler.

These are deliberately narrow. The scheduler has a small, well-defined surface:
submit() takes a RunSpec, returns a run_id, and everything downstream reads from
the run_queue SQLite table. Tests import from here, not from internal modules.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Priority(enum.IntEnum):
    CRITICAL = 1   # chat, urgent nudges
    HIGH     = 2   # interactive /jobs/{name}/run
    NORMAL   = 3   # tick-fired runs
    LOW      = 4   # scheduled cron jobs
    BACKGROUND = 5  # lint, arxiv-digest


class AgentClass(enum.Enum):
    CHAT       = "chat"
    SYNTHESIS  = "synthesis"
    INGEST     = "ingest"
    BACKGROUND = "background"


class RunState(enum.Enum):
    PENDING      = "pending"
    ADMITTED     = "admitted"
    RUNNING      = "running"
    RECONCILING  = "reconciling"
    DONE         = "done"
    FAILED       = "failed"
    CONFLICTED   = "conflicted"
    INTERRUPTED  = "interrupted"


class TriggerSource(enum.Enum):
    CHAT    = "chat"
    TICK    = "tick"
    WATCHER = "watcher"
    JOB     = "job"
    BENCH   = "bench"
    API     = "api"


@dataclass(frozen=True)
class RunSpec:
    """Input to scheduler.submit(). Frozen so callers can't mutate mid-submit."""
    prompt: str
    prompt_family: str
    agent_class: AgentClass
    priority: Priority
    trigger_source: TriggerSource
    model: str = "claude-sonnet-4-6"
    vault_scope: tuple[str, ...] = ()   # empty = full vault
    estimated_in: int = 0
    estimated_out: int = 0
    payload_extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Run:
    """Row view of a run_queue record."""
    id: str
    idempotency_key: str
    state: RunState
    priority: Priority
    agent_class: AgentClass
    trigger_source: TriggerSource
    prompt_family: str
    payload_json: str
    estimated_in: int
    estimated_out: int
    created_at: int
    admitted_at: int | None
    started_at: int | None
    ended_at: int | None
