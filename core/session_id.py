"""Validation helpers for persisted Pi session identifiers."""

from __future__ import annotations

import re
from typing import Final

# Matches Pi's assertValidSessionId grammar: non-empty, alphanumeric at both
# ends, and only alphanumeric / dot / underscore / hyphen in between.
_SESSION_ID_RE: Final = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
)


def is_valid_session_id(value: object) -> bool:
    return isinstance(value, str) and _SESSION_ID_RE.fullmatch(value) is not None
