"""wiki/ops/inbox/ reader + mark-dispatched writer.

Inbox drafts are markdown files the agent writes when it wants to send
something outside the vault (email, slack, gh-issue, gcal-invite). They are
never auto-sent — Yogesh reviews each one, dispatches it by hand, then flips
`dispatched: true` so future evening jobs stop surfacing it.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _vault_root() -> Path:
    return Path(os.environ.get("BRAIN_VAULT_PATH", "/var/brain"))


def _inbox_dir() -> Path:
    return _vault_root() / "wiki" / "ops" / "inbox"


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
# keep it dumb: scalar fields only, no nested objects or lists
_SCALAR_RE = re.compile(r'^([A-Za-z0-9_\-]+):\s*"?(.*?)"?\s*$')


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    fm_block, body = m.group(1), m.group(2)
    fm: dict[str, Any] = {}
    for line in fm_block.splitlines():
        sm = _SCALAR_RE.match(line)
        if not sm:
            continue
        key, val = sm.group(1), sm.group(2)
        if val.lower() in ("true", "false"):
            fm[key] = val.lower() == "true"
        else:
            fm[key] = val
    return fm, body


def list_drafts() -> list[dict[str, Any]]:
    """Return one row per *.md draft under wiki/ops/inbox/, excluding _README.
    Sorted newest first by `drafted-at` (or mtime as fallback)."""
    root = _inbox_dir()
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for md in sorted(root.glob("*.md")):
        if md.name.startswith("_"):
            continue
        try:
            raw = md.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("failed reading %s: %s", md, exc)
            continue
        fm, body = _parse_frontmatter(raw)
        stat = md.stat()
        rows.append(
            {
                "path": str(md.relative_to(_vault_root())),
                "name": md.name,
                "title": fm.get("title") or md.stem,
                "kind": fm.get("kind") or "note",
                "to": fm.get("to"),
                "subject": fm.get("subject"),
                "status": fm.get("status") or "draft",
                "dispatched": bool(fm.get("dispatched")),
                "dispatched_at": fm.get("dispatched-at"),
                "drafted_at": fm.get("drafted-at") or fm.get("created"),
                "expires": fm.get("expires"),
                "mtime": int(stat.st_mtime),
                "body": body.strip(),
            }
        )
    rows.sort(key=lambda r: r.get("drafted_at") or r["mtime"], reverse=True)
    return rows


def _safe_relpath(rel: str) -> Path:
    """Resolve `rel` under vault and refuse to escape wiki/ops/inbox/."""
    root = _vault_root()
    target = (root / rel).resolve()
    inbox = _inbox_dir().resolve()
    try:
        target.relative_to(inbox)
    except ValueError as exc:
        raise ValueError(f"path {rel} outside inbox") from exc
    if not target.is_file():
        raise FileNotFoundError(f"{rel} not found")
    return target


def mark_dispatched(rel_path: str) -> dict[str, Any]:
    """Flip `dispatched: true` + stamp `dispatched-at` in the draft's
    frontmatter. Idempotent — re-dispatching a draft updates the date."""
    target = _safe_relpath(rel_path)
    raw = target.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(raw)
    today = date.today().isoformat()
    fm["dispatched"] = True
    fm["dispatched-at"] = today
    fm["updated"] = today

    # Rewrite frontmatter block — preserve line order for existing keys,
    # append new ones at the end.
    m = _FRONTMATTER_RE.match(raw)
    if m:
        existing_block = m.group(1)
        seen: set[str] = set()
        new_lines: list[str] = []
        for line in existing_block.splitlines():
            sm = _SCALAR_RE.match(line)
            if not sm:
                new_lines.append(line)
                continue
            key = sm.group(1)
            if key in fm:
                new_lines.append(_render_line(key, fm[key]))
                seen.add(key)
            else:
                new_lines.append(line)
        for key in ("dispatched", "dispatched-at", "updated"):
            if key not in seen:
                new_lines.append(_render_line(key, fm[key]))
        new_fm = "\n".join(new_lines)
        body_out = body.lstrip("\n")
        new_raw = f"---\n{new_fm}\n---\n\n{body_out}"
    else:
        # No frontmatter — prepend a minimal one.
        block_lines = [
            _render_line("dispatched", True),
            _render_line("dispatched-at", today),
            _render_line("updated", today),
        ]
        new_raw = "---\n" + "\n".join(block_lines) + "\n---\n\n" + raw.lstrip("\n")

    target.write_text(new_raw, encoding="utf-8")
    return {
        "path": rel_path,
        "dispatched": True,
        "dispatched_at": today,
    }


def _render_line(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return f"{key}: {'true' if value else 'false'}"
    return f"{key}: {value}"
