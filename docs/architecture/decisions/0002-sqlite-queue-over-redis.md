# 0002 — SQLite queue over Redis

**Status:** Accepted
**Date:** 2026-04-14
**Deciders:** Yogesh Seenichamy

## Context
The scheduler needs a durable job queue. Enqueue rate peaks at ~50/min (cron + tick + chat + watcher). The instance is single-node. brain-core already runs an aiosqlite connection in WAL mode with thousands of writes/min without contention.

## Decision
Use a `run_queue` table in the existing SQLite database as the durable queue. No Redis, no RabbitMQ, no SQS. The scheduler polls with 50ms admission and 20ms dispatch loops — well below any rate we care about.

## Alternatives considered
- **Redis Streams.** Rejected: adds a daemon, ~100MB RAM, another failure mode, and brings nothing at this load.
- **SQS.** Rejected: cross-network latency defeats sub-100ms dispatch; extra cost; single-node project.
- **In-memory `asyncio.Queue`.** Rejected: loses work on crash or Spot drain; no introspection for `/runs` queue view.

## Consequences
### Positive
- One durable store; backup is one file
- Debuggable with `sqlite3` CLI / `python3 -c "import sqlite3"`
- `/runs` queue view is a simple `SELECT`
- Survives Spot drain via WAL checkpoint + fsync in the drain sequence
### Negative
- Polling, not push — a 50ms loop is fine, but load-bearing if we ever want lower latency
- Single-writer semantics on the queue table (acceptable; admission is single-threaded anyway)
### Neutral
- Interview story: "polling a well-indexed SQLite table beats a Redis dependency at this scale — prove it with the benchmark"
