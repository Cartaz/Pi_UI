"""Pure helpers for projecting exact document text through Qt text controls."""

from __future__ import annotations


class TextSelectionError(ValueError):
    """Raised when a Qt UTF-16 selection does not map to source text boundaries."""


def qt_plain_text_projection(source: str) -> str:
    """Return the newline form used by Qt's QTextDocument-backed controls.

    QTextDocument normalizes CRLF and lone CR line endings to LF. Keeping this
    conversion explicit means QML never becomes an accidental second owner of
    the canonical document text.
    """

    return source.replace("\r\n", "\n").replace("\r", "\n")


def exact_source_selection(source: str, start_utf16: int, end_utf16: int) -> str:
    """Map a Qt text-control selection back to the exact source substring.

    Qt cursor positions are UTF-16 code-unit offsets in the newline-normalized
    projection. Python slices use Unicode code-point indexes. This mapper also
    restores CRLF/lone-CR separators from the canonical source.
    """

    if start_utf16 < 0 or end_utf16 < 0:
        raise TextSelectionError("selection offsets must be non-negative")
    if end_utf16 < start_utf16:
        start_utf16, end_utf16 = end_utf16, start_utf16

    start_index = _source_index_for_qt_offset(source, start_utf16)
    end_index = _source_index_for_qt_offset(source, end_utf16)
    return source[start_index:end_index]


def _source_index_for_qt_offset(source: str, target_utf16: int) -> int:
    qt_offset = 0
    source_index = 0

    while source_index < len(source):
        if target_utf16 == qt_offset:
            return source_index

        char = source[source_index]
        if char == "\r":
            next_index = source_index + 2 if source.startswith("\r\n", source_index) else source_index + 1
            units = 1
        else:
            next_index = source_index + 1
            units = 2 if ord(char) > 0xFFFF else 1

        next_offset = qt_offset + units
        if qt_offset < target_utf16 < next_offset:
            raise TextSelectionError("selection splits a UTF-16 surrogate pair")

        qt_offset = next_offset
        source_index = next_index

    if target_utf16 == qt_offset:
        return len(source)
    raise TextSelectionError("selection offset exceeds rendered text length")
