from __future__ import annotations

import math

import pytest

from core.agent.protocol import JsonlDecoder, JsonlProtocolError, encode_command


def test_decoder_handles_split_utf8_and_multiple_records() -> None:
    decoder = JsonlDecoder()
    encoded = '{"type":"event","text":"caffè"}\n{"type":"response","success":true}\n'.encode()
    split = encoded.index("è".encode()) + 1

    first = decoder.feed(encoded[:split])
    second = decoder.feed(encoded[split:])

    assert first == []
    assert second == [
        {"type": "event", "text": "caffè"},
        {"type": "response", "success": True},
    ]
    decoder.finish()


def test_decoder_accepts_crlf_but_only_lf_delimits_records() -> None:
    decoder = JsonlDecoder()
    records = decoder.feed(b'{"text":"a\\u2028b"}\r\n')
    assert records == [{"text": "a\u2028b"}]


def test_decoder_rejects_empty_invalid_and_non_object_records() -> None:
    with pytest.raises(JsonlProtocolError, match="empty"):
        JsonlDecoder().feed(b"\n")

    with pytest.raises(JsonlProtocolError, match="valid JSON"):
        JsonlDecoder().feed(b"{broken}\n")

    with pytest.raises(JsonlProtocolError, match="JSON object"):
        JsonlDecoder().feed(b"[]\n")


def test_decoder_rejects_oversized_incomplete_record_and_resets_buffer() -> None:
    decoder = JsonlDecoder(max_record_bytes=5)
    with pytest.raises(JsonlProtocolError, match="byte limit"):
        decoder.feed(b"123456")
    assert decoder.pending_bytes == 0


def test_decoder_reports_partial_record_at_eof_and_resets() -> None:
    decoder = JsonlDecoder()
    decoder.feed(b'{"type":"event"}')
    with pytest.raises(JsonlProtocolError, match="incomplete record"):
        decoder.finish()
    assert decoder.pending_bytes == 0


def test_encode_command_is_compact_utf8_jsonl() -> None:
    assert encode_command({"id": "1", "type": "prompt", "message": "caffè"}) == (
        b'{"id":"1","type":"prompt","message":"caff\xc3\xa8"}\n'
    )


def test_encode_command_rejects_non_finite_numbers() -> None:
    with pytest.raises(JsonlProtocolError, match="serializable"):
        encode_command({"type": "prompt", "temperature": math.nan})
