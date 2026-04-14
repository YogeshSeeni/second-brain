"""Docker container lifecycle for one sandboxed run.

Week 1 form: fire-and-forget docker run + stream attach via the Docker CLI's
`docker run` with stdout piped to the caller. We intentionally avoid the Docker
SDK for W1 because subprocess + stream-json is exactly how v0 brain-core runs
claude -p already — keeping the mental model consistent lowers risk.

W2 adds the local policy proxy + network egress allowlist.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

from .types import ContainerHandle

logger = logging.getLogger(__name__)


def build_docker_run_args(
    *,
    run_id: str,
    image: str,
    worktree_path: Path,
    scratch_path: Path,
    prompt: str,
    prompt_family: str,
    model: str,
) -> list[str]:
    return [
        "docker", "run", "--rm", "-i",
        "--name", f"brain-run-{run_id}",
        "--cpus=1.0",
        "--memory=512m",
        "--memory-swap=512m",
        "--pids-limit=256",
        "--network=brain-runs",
        "--security-opt", "no-new-privileges",
        "--cap-drop=ALL",
        "--mount", f"type=bind,src={worktree_path},dst=/workspace",
        "--mount", f"type=bind,src={scratch_path},dst=/scratch",
        "-e", f"BRAIN_RUN_ID={run_id}",
        "-e", f"BRAIN_PROMPT={prompt}",
        "-e", f"BRAIN_PROMPT_FAMILY={prompt_family}",
        "-e", f"BRAIN_MODEL={model}",
        image,
    ]


async def start_run(
    *,
    run_id: str,
    image: str,
    worktree_path: Path,
    scratch_path: Path,
    prompt: str,
    prompt_family: str,
    model: str,
) -> tuple[ContainerHandle, AsyncIterator[bytes], asyncio.subprocess.Process]:
    """Start the container and return (handle, stdout_stream, process).

    The caller is responsible for iterating stdout_stream until exhaustion and
    awaiting proc.wait() to get the exit code. Use sandbox.exec.stream_run() as
    the glue.
    """
    args = build_docker_run_args(
        run_id=run_id,
        image=image,
        worktree_path=worktree_path,
        scratch_path=scratch_path,
        prompt=prompt,
        prompt_family=prompt_family,
        model=model,
    )
    logger.info("starting sandbox run_id=%s image=%s", run_id, image)

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def stdout_iter() -> AsyncIterator[bytes]:
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield line

    return ContainerHandle(run_id=run_id, container_id=f"brain-run-{run_id}"), stdout_iter(), proc


async def stop_run(handle: ContainerHandle) -> None:
    proc = await asyncio.create_subprocess_exec(
        "docker", "kill", handle.container_id,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
