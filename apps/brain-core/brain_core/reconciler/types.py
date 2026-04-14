from __future__ import annotations

import enum


class ReconcileOutcome(enum.Enum):
    MERGED_FF       = "merged_ff"
    MERGED_THREEWAY = "merged_threeway"
    CONFLICTED      = "conflicted"
    FAILED          = "failed"
