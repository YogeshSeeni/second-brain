-- 0002_run_queue.sql — scheduler run_queue table for brain-v1.

CREATE TABLE IF NOT EXISTS run_queue (
  id                  TEXT PRIMARY KEY,
  idempotency_key     TEXT NOT NULL,
  state               TEXT NOT NULL,            -- pending|admitted|running|reconciling|done|failed|conflicted|interrupted
  priority            INTEGER NOT NULL,         -- 1..5 (1 = CRITICAL)
  agent_class         TEXT NOT NULL,            -- chat|synthesis|ingest|background
  trigger_source      TEXT NOT NULL,            -- chat|tick|watcher|job|bench|api
  prompt_family       TEXT NOT NULL,
  payload_json        TEXT NOT NULL,            -- opaque JSON: prompt, vault_scope, model, etc.
  estimated_in        INTEGER NOT NULL DEFAULT 0,
  estimated_out       INTEGER NOT NULL DEFAULT 0,
  actual_in           INTEGER,
  actual_out          INTEGER,
  cache_read_tokens   INTEGER,
  cache_write_tokens  INTEGER,
  attempt_count       INTEGER NOT NULL DEFAULT 0,
  assigned_container  TEXT,
  worktree_path       TEXT,
  branch_name         TEXT,
  created_at          INTEGER NOT NULL,
  admitted_at         INTEGER,
  started_at          INTEGER,
  ended_at            INTEGER,
  exit_code           INTEGER,
  error_class         TEXT,
  error_detail        TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_queue_state_priority
  ON run_queue(state, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_run_queue_idempotency
  ON run_queue(idempotency_key, created_at);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version  INTEGER PRIMARY KEY,
  applied_at INTEGER NOT NULL
);
