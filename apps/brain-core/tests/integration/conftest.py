import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fake_worker_image() -> str:
    here = Path(__file__).parent / "fake_brain_worker"
    tag = "brain-worker-fake:test"
    subprocess.run(
        ["docker", "build", "--tag", tag, str(here)],
        check=True,
    )
    yield tag


@pytest.fixture
def brain_runs_network() -> str:
    name = "brain-runs"
    subprocess.run(
        ["docker", "network", "inspect", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # create if missing (best-effort; errors OK if already exists)
    subprocess.run(
        ["docker", "network", "create", "--driver", "bridge", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return name
