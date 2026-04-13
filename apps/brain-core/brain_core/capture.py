"""Quick-capture classifier — one-shot `claude -p` subprocess that files a note."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MODEL = os.environ.get("BRAIN_CAPTURE_MODEL", "claude-haiku-4-5")


def _vault_root() -> Path:
    return Path(os.environ.get("BRAIN_VAULT_PATH", "/var/brain"))


_URL_RE = re.compile(r"https?://\S+")


def _slugify(text: str, fallback: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (base or fallback)[:60]


def _default_target(body: str) -> tuple[str, str]:
    """Heuristic fallback when the classifier is unavailable — returns (kind, path)."""
    today = date.today().isoformat()
    if _URL_RE.search(body):
        slug = _slugify(_URL_RE.search(body).group(0), f"capture-{today}")  # type: ignore[union-attr]
        return "reference", f"wiki/sources/{today}-{slug}.md"
    slug = _slugify(body, f"note-{today}")
    return "note", f"wiki/ops/inbox/{today}-{slug}.md"


_CLASSIFIER_PROMPT = """You are a file-placement classifier for a personal second-brain vault.

Read the capture below and respond with ONLY a JSON object, no prose:
  {{
    "kind": "note" | "reference" | "task" | "question" | "evidence",
    "target_path": "<relative path under the vault root, starting with wiki/>",
    "title": "<short slug-friendly title>",
    "summary": "<one sentence>"
  }}

Placement rules:
- URLs → wiki/sources/YYYY-MM-DD-<slug>.md, kind=reference
- Free-form notes → wiki/ops/inbox/YYYY-MM-DD-<slug>.md, kind=note
- Actionable items → wiki/ops/inbox/YYYY-MM-DD-<slug>.md, kind=task
- Open questions → wiki/ops/inbox/YYYY-MM-DD-<slug>.md, kind=question
- Thesis evidence → wiki/thesis/evidence-log.md (append), kind=evidence

Today: {today}

Capture:
{body}
"""


async def _classify(body: str) -> dict | None:
    """Run `claude -p` with a tight JSON prompt. Return parsed dict or None."""
    prompt = _CLASSIFIER_PROMPT.format(today=date.today().isoformat(), body=body)
    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_BIN,
            "-p",
            prompt,
            "--model",
            CLAUDE_MODEL,
            "--output-format",
            "text",
            "--max-turns",
            "1",
            "--dangerously-skip-permissions",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        logger.warning("capture classifier timed out")
        return None
    except FileNotFoundError:
        logger.warning("claude binary %s not found — using heuristic fallback", CLAUDE_BIN)
        return None
    if proc.returncode != 0:
        logger.warning(
            "capture classifier exited %s: %s",
            proc.returncode,
            stderr.decode("utf-8", errors="replace")[:500],
        )
        return None
    text = stdout.decode("utf-8", errors="replace").strip()
    # Tolerate code fences around the JSON
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        logger.warning("capture classifier returned non-JSON: %r", text[:200])
        return None


def _write_capture(kind: str, target_path: str, body: str, summary: str) -> Path:
    """Write the capture to target_path (append for evidence-log, create otherwise)."""
    root = _vault_root()
    dest = root / target_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()

    if target_path.endswith("thesis/evidence-log.md"):
        existing = dest.read_text(encoding="utf-8") if dest.exists() else ""
        entry = f"\n## [{stamp}] {summary or body[:60]}\n\n{body}\n"
        dest.write_text(existing + entry, encoding="utf-8")
        return dest

    if dest.exists():
        # Avoid clobber — suffix with -N
        i = 2
        while True:
            alt = dest.with_stem(f"{dest.stem}-{i}")
            if not alt.exists():
                dest = alt
                break
            i += 1

    frontmatter = (
        "---\n"
        f'title: "{summary or body[:60]}"\n'
        f"created: {stamp}\n"
        f"updated: {stamp}\n"
        f"tags: [capture, {kind}]\n"
        "status: active\n"
        "---\n\n"
    )
    dest.write_text(frontmatter + body + "\n", encoding="utf-8")
    return dest


async def capture(body: str) -> dict:
    """Classify + file a capture. Returns {kind, target_path, summary}."""
    body = body.strip()
    if not body:
        raise ValueError("empty capture")

    cls = await _classify(body)
    if cls and "target_path" in cls and "kind" in cls:
        kind = str(cls.get("kind", "note"))
        target = str(cls["target_path"]).lstrip("/")
        summary = str(cls.get("summary", ""))
    else:
        kind, target = _default_target(body)
        summary = ""

    if not target.startswith("wiki/"):
        # refuse anything outside the vault wiki surface
        kind, target = _default_target(body)

    dest = _write_capture(kind, target, body, summary)
    rel = str(dest.relative_to(_vault_root()))
    return {"kind": kind, "target_path": rel, "summary": summary}


# File-drop path — large or binary captures land in raw/ and a thin
# wiki/sources/ summary wikilinks back to the raw asset. Classifier only sees
# text files; everything else skips classification and goes straight to a
# stub summary page.

_TEXT_EXTS = {
    ".md", ".txt", ".rst", ".org", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".log", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".c", ".cpp",
    ".h", ".hpp", ".cu", ".cuh", ".sql", ".toml", ".ini", ".env.example",
}


def _ext_bucket(ext: str) -> str:
    ext = ext.lower()
    if ext in {".pdf"}:
        return "papers"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".heic"}:
        return "assets"
    if ext in {".csv", ".tsv", ".json", ".jsonl", ".parquet"}:
        return "exports"
    if ext in {".mp3", ".wav", ".m4a", ".flac", ".ogg"}:
        return "assets"
    if ext in {".md", ".txt", ".rst", ".org"}:
        return "docs"
    return "docs"


async def capture_file(filename: str, data: bytes) -> dict:
    """Save an uploaded file to raw/<bucket>/YYYY-MM-DD-<slug><ext> and create
    a wiki/sources/<slug>-summary.md stub. If the file is text-ish and small,
    also run the classifier on the content so it can wikilink into the right
    concept/entity pages.

    Returns {raw_path, summary_path, kind, summary, classified}.
    """
    if not filename:
        raise ValueError("missing filename")
    if not data:
        raise ValueError("empty file")

    root = _vault_root()
    stamp = date.today().isoformat()
    stem = Path(filename).stem or "capture"
    ext = Path(filename).suffix or ""
    bucket = _ext_bucket(ext)
    slug = _slugify(stem, f"capture-{stamp}")

    raw_dir = root / "raw" / bucket
    raw_dir.mkdir(parents=True, exist_ok=True)

    raw_name = f"{stamp}-{slug}{ext}"
    raw_dest = raw_dir / raw_name
    i = 2
    while raw_dest.exists():
        raw_dest = raw_dir / f"{stamp}-{slug}-{i}{ext}"
        i += 1
    raw_dest.write_bytes(data)

    rel_raw = str(raw_dest.relative_to(root))

    # If text-ish and under a token budget, read + classify so the summary
    # page inherits the real kind/summary/cross-refs.
    classified = False
    classifier_summary = ""
    text_body: str | None = None
    is_text = ext.lower() in _TEXT_EXTS
    if is_text and len(data) < 256 * 1024:
        try:
            text_body = data.decode("utf-8", errors="replace")
        except Exception:
            text_body = None
    if text_body:
        cls = await _classify(text_body)
        if cls and "kind" in cls:
            classifier_summary = str(cls.get("summary", ""))
            classified = True

    summary_slug = _slugify(stem, f"capture-{stamp}")
    summary_path = root / "wiki" / "sources" / f"{stamp}-{summary_slug}-summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    i = 2
    while summary_path.exists():
        summary_path = (
            root / "wiki" / "sources" / f"{stamp}-{summary_slug}-{i}-summary.md"
        )
        i += 1

    title = classifier_summary or stem
    body_block = (
        f"Raw source: [[{rel_raw}]]\n\n"
        f"**Filename:** `{filename}`  \n"
        f"**Size:** {len(data)} bytes  \n"
        f"**Bucket:** `raw/{bucket}/`\n"
    )
    if classifier_summary:
        body_block += f"\n## Classifier summary\n\n{classifier_summary}\n"
    if text_body and len(text_body) < 8000:
        body_block += f"\n## Excerpt\n\n```\n{text_body[:4000]}\n```\n"

    frontmatter = (
        "---\n"
        f'title: "{title}"\n'
        f"created: {stamp}\n"
        f"updated: {stamp}\n"
        "tags: [capture, file-drop]\n"
        'type: "doc"\n'
        "status: active\n"
        f'raw-path: "{rel_raw}"\n'
        "---\n\n"
    )
    summary_path.write_text(frontmatter + body_block, encoding="utf-8")

    return {
        "raw_path": rel_raw,
        "summary_path": str(summary_path.relative_to(root)),
        "kind": "file",
        "summary": classifier_summary,
        "classified": classified,
    }
