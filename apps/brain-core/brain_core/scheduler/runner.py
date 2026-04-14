"""Long-running coroutines for the scheduler loops.

start_scheduler(run_one) launches the admission and dispatch loops as background
tasks bound to the current event loop. Returns an opaque handle that can be
awaited on shutdown to cancel cleanly.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .admission import run_admission_pass
from .dispatch import run_dispatch_pass

logger = logging.getLogger(__name__)

ADMISSION_INTERVAL_SEC = 0.05  # 50ms per design D9
DISPATCH_INTERVAL_SEC  = 0.02  # 20ms


@dataclass
class SchedulerHandle:
    admission_task: asyncio.Task
    dispatch_task:  asyncio.Task

    async def stop(self) -> None:
        for t in (self.admission_task, self.dispatch_task):
            t.cancel()
        for t in (self.admission_task, self.dispatch_task):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


async def _admission_loop() -> None:
    while True:
        try:
            await run_admission_pass()
        except Exception:
            logger.exception("admission pass crashed")
        await asyncio.sleep(ADMISSION_INTERVAL_SEC)


async def _dispatch_loop(run_one) -> None:
    while True:
        try:
            await run_dispatch_pass(run_one)
        except Exception:
            logger.exception("dispatch pass crashed")
        await asyncio.sleep(DISPATCH_INTERVAL_SEC)


def start_scheduler(run_one) -> SchedulerHandle:
    return SchedulerHandle(
        admission_task=asyncio.create_task(_admission_loop(), name="brain.scheduler.admission"),
        dispatch_task=asyncio.create_task(_dispatch_loop(run_one), name="brain.scheduler.dispatch"),
    )
