from __future__ import annotations

import pytest

from ui.text_projection import (
    TextSelectionError,
    exact_source_selection,
    qt_plain_text_projection,
)


def test_projection_normalizes_qt_newlines_without_changing_source() -> None:
    source = "a\r\nb\rc\nd 🌍\r\n"

    assert qt_plain_text_projection(source) == "a\nb\nc\nd 🌍\n"
    assert source == "a\r\nb\rc\nd 🌍\r\n"


def test_exact_selection_restores_crlf_lone_cr_and_non_bmp_text() -> None:
    source = "a\r\nb\rc\nd 🌍\r\n"

    # Rendered UTF-16 offsets: a(1), LF(1), b(1), LF(1), c(1), LF(1),
    # d(1), space(1), globe(2), LF(1) = 11 total.
    assert exact_source_selection(source, 0, 11) == source
    assert exact_source_selection(source, 11, 0) == source
    assert exact_source_selection(source, 2, 4) == "b\r"
    assert exact_source_selection(source, 6, 10) == "d 🌍"


def test_exact_selection_rejects_surrogate_split_and_out_of_range_offsets() -> None:
    source = "x🌍y"

    with pytest.raises(TextSelectionError, match="surrogate pair"):
        exact_source_selection(source, 1, 2)

    with pytest.raises(TextSelectionError, match="exceeds"):
        exact_source_selection(source, 0, 5)

    with pytest.raises(TextSelectionError, match="non-negative"):
        exact_source_selection(source, -1, 0)
