import json
import pytest

from brain_core.sandbox.exec import parse_stream_json, StreamParseResult


def _lines(events: list[dict]) -> list[bytes]:
    return [(json.dumps(e) + "\n").encode() for e in events]


def test_parse_captures_final_text_and_usage():
    events = [
        {"type": "message_start", "message": {"id": "m1"}},
        {"type": "stream_event", "event": {"type": "content_block_start",
            "content_block": {"type": "text", "text": ""}}},
        {"type": "stream_event", "event": {"type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Hello "}}},
        {"type": "stream_event", "event": {"type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "world"}}},
        {"type": "result", "result": "Hello world",
         "usage": {"input_tokens": 42, "output_tokens": 7,
                   "cache_read_input_tokens": 30, "cache_creation_input_tokens": 0}},
    ]
    result = parse_stream_json(_lines(events))
    assert isinstance(result, StreamParseResult)
    assert result.final_text == "Hello world"
    assert result.input_tokens == 42
    assert result.output_tokens == 7
    assert result.cache_read_tokens == 30
    assert result.cache_write_tokens == 0
    assert len(result.events) == 5


def test_parse_tolerates_garbage_lines():
    lines = [
        b"not-json\n",
        b'{"type": "result", "result": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}\n',
    ]
    result = parse_stream_json(lines)
    assert result.final_text == "ok"
    # Garbage lines are skipped, not fatal
    assert result.input_tokens == 1
