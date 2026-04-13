"""Loaders for voice.md, thesis pages, and CLAUDE.md — injected into every prompt."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _vault_root() -> Path:
    return Path(os.environ.get("BRAIN_VAULT_PATH", "/Users/yogeshseenichamy/second-brain"))


def load_voice() -> str:
    """Read wiki/voice.md if present; empty string on miss."""
    path = _vault_root() / "wiki" / "voice.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("voice.md missing at %s", path)
        return ""
    except OSError as exc:
        logger.exception("failed reading voice.md: %s", exc)
        return ""


def load_thesis() -> str:
    """Concatenate every .md file under wiki/thesis/ with file-name separators."""
    root = _vault_root() / "wiki" / "thesis"
    if not root.exists():
        return ""
    parts: list[str] = []
    for md in sorted(root.rglob("*.md")):
        try:
            parts.append(f"## {md.relative_to(root)}\n\n{md.read_text(encoding='utf-8')}")
        except OSError as exc:
            logger.warning("failed reading thesis file %s: %s", md, exc)
    return "\n\n---\n\n".join(parts)


def load_claude_md() -> str:
    """Read the vault's CLAUDE.md; empty string on miss."""
    path = _vault_root() / "CLAUDE.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.exception("failed reading CLAUDE.md: %s", exc)
        return ""


def build_system_prompt() -> str:
    """Compose the voice + thesis + CLAUDE.md system prompt block."""
    voice = load_voice()
    thesis = load_thesis()
    claude_md = load_claude_md()
    return (
        "# Who you are (voice.md)\n\n"
        + voice
        + "\n\n# Thesis state\n\n"
        + thesis
        + "\n\n# CLAUDE.md\n\n"
        + claude_md
    )
