# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Helpers shared by the structured-format handlers (TOML, YAML, JSON).

``.properties``, regex, and plain don't share anything beyond the
:class:`.FileFormat` Protocol — they live entirely inside their
respective module.
"""

from __future__ import annotations

from ._base import FormatError


def split_key(key: str) -> list[str]:
    """Split a dotted key path into segments, rejecting empty results."""
    parts = [part for part in key.split(".") if part]
    if not parts:
        raise FormatError(f"empty key: {key!r}")
    return parts


def navigate(root, parts: list[str], create: bool):
    """Walk ``root`` along ``parts``, returning ``(parent, last_part)``.

    With ``create=True``, missing intermediate dicts are inserted along
    the way; with ``create=False`` a missing segment raises
    :class:`.FormatError`.
    """
    cursor = root
    for part in parts[:-1]:
        if part not in cursor:
            if not create:
                raise FormatError(f"missing key {part!r} while reading")
            cursor[part] = {}
        cursor = cursor[part]
    return cursor, parts[-1]
