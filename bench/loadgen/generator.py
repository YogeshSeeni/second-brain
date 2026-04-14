"""Async submission generator. Hands Submitted run_ids back to the caller."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

from brain_core.scheduler import (
    AgentClass, Priority, RunSpec, TriggerSource, submit,
)


_PROMPT_FIXTURES = [
    ("smoke-a", "say hi from bench-a"),
    ("smoke-b", "say hi from bench-b"),
    ("smoke-c", "say hi from bench-c"),
]


@dataclass
class SubmissionResult:
    run_id: str
    submitted_at: float
    family: str


async def submit_one() -> SubmissionResult:
    family, prompt = random.choice(_PROMPT_FIXTURES)
    run_id = await submit(RunSpec(
        prompt=prompt,
        prompt_family=family,
        agent_class=AgentClass.BACKGROUND,
        priority=Priority.BACKGROUND,
        trigger_source=TriggerSource.BENCH,
        payload_extra={"bench_t": time.time_ns()},
    ))
    return SubmissionResult(
        run_id=run_id,
        submitted_at=time.time(),
        family=family,
    )


async def run_sustained(concurrency: int, duration_sec: int) -> list[SubmissionResult]:
    end = time.time() + duration_sec
    results: list[SubmissionResult] = []
    in_flight: set[asyncio.Task] = set()

    while time.time() < end or in_flight:
        while time.time() < end and len(in_flight) < concurrency:
            t = asyncio.create_task(submit_one())
            in_flight.add(t)
        done, _ = await asyncio.wait(in_flight, timeout=0.5,
                                     return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            in_flight.remove(t)
            results.append(await t)

    return results
