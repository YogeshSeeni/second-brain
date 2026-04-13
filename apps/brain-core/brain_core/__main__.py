"""`python -m brain_core` entry — runs uvicorn against the app."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("brain_core.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
