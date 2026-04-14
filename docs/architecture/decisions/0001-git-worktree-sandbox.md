# 0001 — git-worktree sandbox

**Status:** Accepted
**Date:** 2026-04-14
**Deciders:** Yogesh Seenichamy

## Context
brain v0 runs agents bare-metal as `claude -p` subprocesses against the live vault. This works for one agent. It breaks down immediately with concurrent agents: writes race, reads see partial state, nothing is isolated from anything else. The design calls for 10–20 concurrent agents on one node.

## Decision
Every agent run executes inside a short-lived git worktree carved from a bare `/var/brain/vault.git` repo. The live reader (brain-core routes, watcher) reads from `/var/brain/worktrees/main/`, which is itself just a long-lived worktree on branch `main`. Per-run worktrees live at `/var/brain/worktrees/run-<uuid>/` on branch `agent/run-<uuid>`. When a run finishes, a reconciler fast-forwards (or three-way merges) the run's branch back into `main` and deletes the worktree.

## Alternatives considered
- **Shared bind mount with file locks.** Rejected: locks don't compose with agent edits, and conflicts become silent.
- **Separate full clones per run.** Rejected: cost of cloning grows with vault size; worktrees share the object store.
- **Copy-on-write via overlayfs.** Rejected: Linux-specific, brittle across kernels, hard to reason about, no natural merge story.
- **Firecracker microVMs.** Rejected: too expensive for t4g.large; wrong instance family.

## Consequences
### Positive
- Natural isolation primitive — git already models parallel work
- Conflicts become first-class: the reconciler can three-way merge or file a conflict draft
- Sparse-checkout supports scoped runs (~80ms for scoped, ~400ms for full)
- Shared object store keeps disk cost bounded
### Negative
- `git gc` must be disabled on the bare repo to keep unresolved branches alive
- Worktree creation is on the critical path for run latency (mitigated by sparse-checkout)
- Adds operational complexity to backup/restore (one directory, multiple worktrees)
### Neutral
- Every agent run has a durable branch name — tracing, audit, and rollback all become easy
