"""Parse stream-json output from a containerized claude -p run.

The host iterates the container's stdout line-by-line, feeds lines through
parse_stream_json(), and collects a StreamParseResult. Each line is a JSON
envelope; we care about two kinds: text deltas for progressive fan-out, and
the final `result` event for the token usage block.

Tool-use and thinking blocks are observed but not surfaced in W1 — they become
spans in W2 once the decorator-driven instrumentation lands.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass
class StreamParseResult:
    final_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    events: list[dict] = field(default_factory=list)


def parse_stream_json(lines: Iterable[bytes]) -> StreamParseResult:
    result = StreamParseResult()
    accumulated_deltas: list[str] = []

    for raw in lines:
        try:
            event = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.debug("skipping non-JSON stream line: %r", raw[:200])
            continue

        result.events.append(event)
        etype = event.get("type")

        if etype == "stream_event":
            inner = event.get("event", {})
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta":
                    accumulated_deltas.append(delta.get("text", ""))

        elif etype == "result":
            result.final_text = event.get("result") or "".join(accumulated_deltas)
            usage = event.get("usage") or {}
            result.input_tokens  = int(usage.get("input_tokens", 0))
            result.output_tokens = int(usage.get("output_tokens", 0))
            result.cache_read_tokens  = int(usage.get("cache_read_input_tokens", 0))
            result.cache_write_tokens = int(usage.get("cache_creation_input_tokens", 0))

    if not result.final_text and accumulated_deltas:
        result.final_text = "".join(accumulated_deltas)

    return result
