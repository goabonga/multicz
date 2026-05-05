# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""JSON handler — preserves key order and detected indentation.

The stdlib :mod:`json` module already round-trips key order. The
indent is detected from the first indented line in the existing file
so a ``package.json`` that uses 2 spaces stays at 2 spaces, a
``Chart.json`` at 4 stays at 4, etc.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

from ._base import FormatError
from ._common import navigate, split_key


def _detect_indent(text: str) -> int:
    """Best-effort indent detection: width of the first indented line."""
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        if stripped and stripped != line:
            return len(line) - len(stripped)
    return 2


class JsonFormat:
    name = "json"

    def matches(self, file: Path, key: str | None) -> bool:
        return key is not None and file.suffix.lower() == ".json"

    def read(self, file: Path, key: str | None) -> str:
        assert key is not None
        parts = split_key(key)
        text = file.read_text(encoding="utf-8")
        data = _json.loads(text or "{}")
        cursor, last = navigate(data, parts, create=False)
        if last not in cursor:
            raise FormatError(f"key {key!r} not found in {file}")
        return str(cursor[last])

    def write(self, file: Path, key: str | None, value: str) -> None:
        assert key is not None
        parts = split_key(key)
        text = file.read_text(encoding="utf-8")
        indent = _detect_indent(text)
        data = _json.loads(text or "{}")
        cursor, last = navigate(data, parts, create=True)
        cursor[last] = value
        rendered = _json.dumps(data, indent=indent, ensure_ascii=False)
        file.write_text(rendered + "\n", encoding="utf-8")
