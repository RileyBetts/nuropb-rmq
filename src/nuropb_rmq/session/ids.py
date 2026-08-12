# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Session-layer correlation id validation and generation."""

from __future__ import annotations

import re
import uuid

# AMQP shortstr ≤255 octets; UUID4 hex default (32 ascii chars).
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")


class InvalidIdError(ValueError):
    """Id failed format validation (reject, never coerce)."""


class IdCollisionError(ValueError):
    """Caller-supplied id collides with an outstanding correlation entry."""


def validate_id(value: str) -> str:
    if not isinstance(value, str):
        raise InvalidIdError("id must be a string")
    raw = value.encode("utf-8")
    if len(raw) == 0 or len(raw) > 255:
        raise InvalidIdError("id must be 1..255 UTF-8 octets")
    if not _SAFE_ID.match(value):
        raise InvalidIdError("id must be ASCII safe subset (A-Za-z0-9._:-)")
    return value


def generate_id() -> str:
    return uuid.uuid4().hex
