"""Loaders for voice.md, thesis pages, and CLAUDE.md — injected into every prompt.

Also houses the topic-thread context resolver: when a topic thread runs a turn,
we narrow the vault excerpt included in the prompt to pages that overlap in
keywords with the thread title + last few user messages, rather than dumping
the whole wiki.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "about", "after", "again", "against", "also", "been", "before", "being",
    "between", "both", "could", "does", "doing", "down", "during", "each",
    "from", "further", "have", "having", "here", "into", "itself", "just",
    "more", "most", "only", "other", "over", "same", "should", "some",
    "such", "than", "that", "their", "them", "then", "there", "these",
    "they", "this", "those", "through", "under", "until", "very", "were",
    "what", "when", "where", "which", "while", "will", "with", "would",
    "your", "yours",
}
_WORD_RE = re.compile(r"[a-z][a-z0-9\-]{3,}")
_TOPIC_SCOPE_K = 5
_TOPIC_SCOPE_CHARS = 800
_TOPIC_SCOPE_EXCLUDE_DIRS = ("thesis",)
_TOPIC_SCOPE_EXCLUDE_FILES = ("voice.md", "log.md", "index.md")


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


def _tokenize(text: str) -> set[str]:
    """Lowercase, keep alphanumeric words ≥4 chars, drop stopwords."""
    return {
        w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS
    }


def _iter_wiki_pages() -> list[Path]:
    root = _vault_root() / "wiki"
    if not root.is_dir():
        return []
    out: list[Path] = []
    for md in root.rglob("*.md"):
        rel = md.relative_to(root)
        if rel.parts and rel.parts[0] in _TOPIC_SCOPE_EXCLUDE_DIRS:
            continue
        if md.name in _TOPIC_SCOPE_EXCLUDE_FILES:
            continue
        out.append(md)
    return out


def resolve_topic_context(title: str, recent_user_messages: list[str]) -> str:
    """Return a markdown block of top-K wiki pages keyword-matched to the
    thread title + recent user messages. Empty string if nothing scores."""
    query = " ".join([title, *recent_user_messages]).strip()
    if not query:
        return ""
    keywords = _tokenize(query)
    if not keywords:
        return ""

    root = _vault_root() / "wiki"
    scored: list[tuple[int, Path, str]] = []
    for md in _iter_wiki_pages():
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        tokens = _tokenize(text)
        hits = len(keywords & tokens)
        if hits <= 0:
            continue
        scored.append((hits, md, text))

    if not scored:
        return ""

    scored.sort(key=lambda row: (-row[0], str(row[1])))
    top = scored[:_TOPIC_SCOPE_K]
    parts: list[str] = []
    for hits, md, text in top:
        rel = md.relative_to(root)
        excerpt = text[:_TOPIC_SCOPE_CHARS]
        if len(text) > _TOPIC_SCOPE_CHARS:
            excerpt = excerpt.rstrip() + "\n\n…truncated…"
        parts.append(f"## wiki/{rel}  (score {hits})\n\n{excerpt}")
    return "\n\n---\n\n".join(parts)


def build_system_prompt(
    thread_kind: str = "main",
    thread_title: str | None = None,
    recent_user_messages: list[str] | None = None,
) -> str:
    """Compose the system prompt block.

    For topic threads, append a scoped vault-context section built from the
    top-K wiki pages whose keywords overlap the title + recent user turns.
    """
    voice = load_voice()
    thesis = load_thesis()
    claude_md = load_claude_md()
    base = (
        "# Who you are (voice.md)\n\n"
        + voice
        + "\n\n# Thesis state\n\n"
        + thesis
        + "\n\n# CLAUDE.md\n\n"
        + claude_md
    )
    if thread_kind != "topic" or not thread_title:
        return base
    topic_context = resolve_topic_context(thread_title, recent_user_messages or [])
    if not topic_context:
        return base
    return (
        base
        + "\n\n# Topic thread context\n\n"
        + f"This turn runs on topic thread `{thread_title}`. The following "
        + "wiki pages were selected by keyword overlap with the thread title "
        + "and recent user messages. Prefer these as grounding over the full "
        + "vault, but still read linked pages on-demand if something obvious "
        + "is missing.\n\n"
        + topic_context
    )
