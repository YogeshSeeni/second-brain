"""Vault filesystem watcher.

Watches `wiki/` for edits and, after a 30-second quiet period (so a flurry
of saves coalesces into one event), drops a nudge summarizing what moved.

Design note: watchdog's Observer runs on its own OS thread and calls our
handler from that thread. The handler just writes into an `asyncio.Queue`
via `loop.call_soon_threadsafe`, so everything downstream — debounce
timer, nudge creation — stays on the main event loop.

For now a change event produces a simple `kind='watcher'` nudge. The plan's
full vision (re-ingest + cross-ref + thesis check) can replace the nudge
with a real agent turn once we trust the signal volume.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from . import db

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 30
POLL_INTERVAL_SECONDS = 5
IGNORED_SUFFIXES = (".swp", ".swx", ".tmp", "~")


class _QueueHandler(FileSystemEventHandler):
    """Pushes (timestamp, relpath) tuples into an asyncio queue from the
    watchdog worker thread via call_soon_threadsafe."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[tuple[float, str]],
        root: Path,
    ) -> None:
        self._loop = loop
        self._queue = queue
        self._root = root

    def _emit(self, path: str) -> None:
        if path.endswith(IGNORED_SUFFIXES):
            return
        try:
            rel = str(Path(path).relative_to(self._root))
        except ValueError:
            rel = path
        # .put_nowait is safe from another thread as long as we schedule it
        # via call_soon_threadsafe.
        self._loop.call_soon_threadsafe(
            self._queue.put_nowait, (time.time(), rel)
        )

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(getattr(event, "dest_path", event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(event.src_path)


async def _debounce_loop(queue: asyncio.Queue[tuple[float, str]]) -> None:
    """Consume events, coalesce by DEBOUNCE_SECONDS of quiet, emit a nudge."""
    last_event_ts: float | None = None
    changed: set[str] = set()
    while True:
        try:
            # Wake at least every POLL_INTERVAL_SECONDS so we can fire once
            # the quiet window has elapsed even without new events.
            ts, rel = await asyncio.wait_for(
                queue.get(), timeout=POLL_INTERVAL_SECONDS
            )
            last_event_ts = ts
            changed.add(rel)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            raise

        if last_event_ts is None or not changed:
            continue
        if time.time() - last_event_ts < DEBOUNCE_SECONDS:
            continue

        paths = sorted(changed)
        count = len(paths)
        preview = ", ".join(paths[:3])
        if count > 3:
            preview += f", +{count - 3} more"
        body = f"vault edits settled: {count} file(s) — {preview}"
        try:
            await db.create_nudge(kind="watcher", body=body, source_ref=None)
        except Exception as exc:  # noqa: BLE001
            logger.exception("watcher nudge write failed: %s", exc)
        logger.info("watcher debounce fired: %s", body)

        last_event_ts = None
        changed.clear()


class WatcherHandle:
    """Bundle of the Observer + debounce task so the lifespan can shut
    both down cleanly."""

    __slots__ = ("observer", "task")

    def __init__(self, observer: Observer, task: asyncio.Task[None]) -> None:
        self.observer = observer
        self.task = task

    async def aclose(self) -> None:
        self.task.cancel()
        try:
            await self.task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            self.observer.stop()
            self.observer.join(timeout=2.0)
        except Exception:  # noqa: BLE001
            logger.exception("watcher observer shutdown raised")


async def start_watcher(vault_path: str) -> WatcherHandle | None:
    """Mount an Observer on `vault_path/wiki` and spawn the debounce loop.

    Returns a WatcherHandle, or None if the wiki directory is missing."""
    wiki = Path(vault_path) / "wiki"
    if not wiki.is_dir():
        logger.warning("watcher: %s not found, not starting", wiki)
        return None

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[float, str]] = asyncio.Queue()
    handler = _QueueHandler(loop, queue, wiki)
    observer = Observer()
    observer.schedule(handler, str(wiki), recursive=True)
    observer.daemon = True
    observer.start()
    logger.info("watcher observing %s", wiki)

    task = asyncio.create_task(_debounce_loop(queue), name="watcher-debounce")
    return WatcherHandle(observer=observer, task=task)


VAULT_PATH = os.environ.get("BRAIN_VAULT_PATH", "/var/brain")
