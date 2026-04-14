"""Load profile definitions for bench/run.py."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Profile(enum.Enum):
    RAMP      = "ramp"
    SUSTAINED = "sustained"
    BURST     = "burst"
    MIXED     = "mixed"


@dataclass(frozen=True)
class ProfileConfig:
    profile:     Profile
    concurrency: int
    duration_sec: int


def parse_duration(s: str) -> int:
    """'5m' → 300, '30s' → 30, '1h' → 3600."""
    unit = s[-1].lower()
    value = int(s[:-1])
    return {"s": 1, "m": 60, "h": 3600}[unit] * value
