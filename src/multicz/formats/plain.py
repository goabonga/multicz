# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Plain text files holding only a version literal.

When ``key`` is ``None``, the *entire* file content is the version
(stripped of surrounding whitespace on read, written with a trailing
newline). Used by ``VERSION`` files, Helm chart subcharts that ship
just the version string, etc.
"""

from __future__ import annotations

from pathlib import Path


class PlainFormat:
    name = "plain"

    def matches(self, file: Path, key: str | None) -> bool:
        return key is None

    def read(self, file: Path, key: str | None) -> str:
        return file.read_text(encoding="utf-8").strip()

    def write(self, file: Path, key: str | None, value: str) -> None:
        file.write_text(value + "\n", encoding="utf-8")
