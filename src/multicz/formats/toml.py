# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""TOML handler — preserves comments, key order, and whitespace.

Reads via :mod:`tomlkit`'s round-trip parser so a ``write`` that bumps
``[project].version = "1.2.3"`` to ``"1.3.0"`` leaves every other byte
of the file untouched, including blank lines and trailing comments
on the same key.
"""

from __future__ import annotations

from pathlib import Path

import tomlkit

from ._base import FormatError
from ._common import navigate, split_key


class TomlFormat:
    name = "toml"

    def matches(self, file: Path, key: str | None) -> bool:
        return key is not None and file.suffix.lower() == ".toml"

    def read(self, file: Path, key: str | None) -> str:
        assert key is not None
        parts = split_key(key)
        doc = tomlkit.parse(file.read_text(encoding="utf-8"))
        cursor, last = navigate(doc, parts, create=False)
        if last not in cursor:
            raise FormatError(f"key {key!r} not found in {file}")
        return str(cursor[last])

    def write(self, file: Path, key: str | None, value: str) -> None:
        assert key is not None
        parts = split_key(key)
        doc = tomlkit.parse(file.read_text(encoding="utf-8"))
        cursor, last = navigate(doc, parts, create=True)
        cursor[last] = value
        file.write_text(tomlkit.dumps(doc), encoding="utf-8")
