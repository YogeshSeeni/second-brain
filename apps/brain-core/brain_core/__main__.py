"""`python -m brain_core` entry — runs uvicorn against the app."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("BRAIN_CORE_HOST", "127.0.0.1")
    port = int(os.environ.get("BRAIN_CORE_PORT", "8000"))
    uvicorn.run("brain_core.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
