"""Vault filesystem watcher — STUB until Day 3.

Day 3 wires this up with `watchdog.Observer` and a 30s debounce, enqueuing
'review edits + update cross-refs + check thesis alignment' jobs on any
change under `wiki/`.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def start_watcher(vault_path: str, queue: asyncio.Queue) -> None:
    """No-op until Day 3."""
    logger.info("watcher stub — Day 3 (vault=%s)", vault_path)
