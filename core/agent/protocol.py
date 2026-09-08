"""Protocol helpers for Pi RPC mode.

Pi RPC uses strict LF-delimited JSON (JSONL) over stdin/stdout. This module is
Qt-free so framing and validation can be tested independently from QProcess.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

JsonObject = dict[str, Any]


class JsonlProtocolError(ValueError):
    """Raised when the RPC byte stream violates the framing contract."""


class JsonlDecoder:
    """Incrementally decode strict LF-delimited JSON objects.

    Bytes are buffered until an ASCII LF is received. Decoding UTF-8 only
    after a complete frame naturally handles multi-byte code points split over
    arbitrary QProcess chunks. CRLF input is accepted by stripping a single
    CR immediately before LF, matching Pi's RPC documentation.
    """

    def __init__(self, *, max_record_bytes: int = 8 * 1024 * 1024) -> None:
        if max_record_bytes <= 0:
            raise ValueError("max_record_bytes must be positive")
        self._max_record_bytes = max_record_bytes
        self._buffer = bytearray()

    @property
    def pending_bytes(self) -> int:
        """Number of bytes currently buffered for an incomplete record."""

        return len(self._buffer)

    def feed(self, chunk: bytes | bytearray | memoryview) -> list[JsonObject]:
        """Feed bytes and return all complete JSON objects found in the chunk."""

        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("chunk must be bytes-like")

        self._buffer.extend(chunk)
        records: list[JsonObject] = []

        while True:
            lf_index = self._buffer.find(b"\n")
            if lf_index < 0:
                if len(self._buffer) > self._max_record_bytes:
                    self._buffer.clear()
                    raise JsonlProtocolError("RPC record exceeds configured byte limit")
                break

            frame = bytes(self._buffer[:lf_index])
            del self._buffer[: lf_index + 1]

            if frame.endswith(b"\r"):
                frame = frame[:-1]

            if not frame:
                raise JsonlProtocolError("empty RPC record")
            if len(frame) > self._max_record_bytes:
                raise JsonlProtocolError("RPC record exceeds configured byte limit")

            try:
                text = frame.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise JsonlProtocolError("RPC record is not valid UTF-8") from exc

            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise JsonlProtocolError("RPC record is not valid JSON") from exc

            if not isinstance(payload, dict):
                raise JsonlProtocolError("RPC record must be a JSON object")

            records.append(payload)

        return records

    def finish(self) -> None:
        """Validate that EOF did not leave a partial JSONL record behind."""

        if self._buffer:
            pending = len(self._buffer)
            self._buffer.clear()
            raise JsonlProtocolError(
                f"RPC stream ended with an incomplete record ({pending} bytes)"
            )


def encode_command(command: Mapping[str, Any]) -> bytes:
    """Encode one Pi RPC command as compact UTF-8 JSON followed by LF."""

    if not isinstance(command, Mapping):
        raise TypeError("command must be a mapping")
    if not command:
        raise ValueError("command must not be empty")

    try:
        encoded = json.dumps(
            dict(command),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise JsonlProtocolError("command is not JSON serializable") from exc

    return encoded + b"\n"
