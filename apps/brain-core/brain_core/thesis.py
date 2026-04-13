"""Leverage-thesis aggregator — reads wiki/thesis/ for the /thesis route.

Pure file reads. No SQLite. The axis pages and evidence log are the source
of truth; this module parses frontmatter + section content and returns a
JSON shape the web app can render without having to understand markdown.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AXES = ("research", "industry", "skills", "optionality")
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_EVIDENCE_ROW_RE = re.compile(
    r"^##\s+(\d{4}-\d{2}-\d{2})\s+—\s+(\w+)\s+—\s+(.+?)$",
    re.MULTILINE,
)


def _vault_root() -> Path:
    return Path(os.environ.get("BRAIN_VAULT_PATH", "/var/brain"))


def _thesis_dir() -> Path:
    return _vault_root() / "wiki" / "thesis"


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _extract_section(text: str, heading: str) -> str:
    """Return the body of a `## heading` section, trimmed. Empty if missing."""
    pattern = rf"^##\s+{re.escape(heading)}\s*\n(.+?)(?=\n##\s|\Z)"
    m = re.search(pattern, text, re.DOTALL | re.MULTILINE | re.IGNORECASE)
    if not m:
        return ""
    body = m.group(1).strip()
    # Drop the HTML comment placeholders the stub pages ship with.
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL).strip()
    return body


def _parse_confidence(raw: str) -> float | None:
    if not raw or raw.lower() in ("unreviewed", "none", "null"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _read_axis(name: str) -> dict[str, Any]:
    path = _thesis_dir() / f"{name}.md"
    if not path.exists():
        return {
            "axis": name,
            "present": False,
            "confidence": None,
            "updated": None,
            "stance": "",
            "open_questions": [],
        }
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("failed to read %s: %s", path, exc)
        return {"axis": name, "present": False, "error": str(exc)}

    fm = _parse_frontmatter(text)
    stance = _extract_section(text, "Current stance")
    questions_raw = _extract_section(text, "Open questions")
    open_questions = [
        re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
        for line in questions_raw.splitlines()
        if line.strip().startswith(("-", "*"))
    ]
    return {
        "axis": name,
        "present": True,
        "confidence": _parse_confidence(fm.get("confidence", "")),
        "confidence_raw": fm.get("confidence"),
        "updated": fm.get("updated"),
        "stance": stance,
        "open_questions": open_questions,
    }


def _read_evidence(limit: int = 10) -> list[dict[str, Any]]:
    path = _thesis_dir() / "evidence-log.md"
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for m in _EVIDENCE_ROW_RE.finditer(text):
        rows.append(
            {
                "date": m.group(1),
                "axis": m.group(2),
                "claim": m.group(3).strip(),
            }
        )
    # Evidence log is append-only, newest at bottom — reverse for "recent first".
    rows.reverse()
    return rows[:limit]


async def get_thesis() -> dict[str, Any]:
    """Return the four axis summaries + recent evidence rows."""
    axes = [_read_axis(name) for name in AXES]
    evidence = _read_evidence(limit=10)
    return {"axes": axes, "evidence": evidence}
