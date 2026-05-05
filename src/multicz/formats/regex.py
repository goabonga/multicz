# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Regex escape hatch for languages without a native structured manifest.

A ``key`` prefixed with ``regex:`` is a language-agnostic accessor:
the rest of the string is a regex with one capture group locating the
version literal. Useful for ``__version__ = "X"`` in Python,
``export const VERSION = "X"`` in TypeScript, ``VERSION := X`` in
Makefiles, etc. The regex is anchored with :data:`re.MULTILINE`, and
only the *first* match's capture group is rewritten — surrounding
text (quotes, indentation, comments) is preserved byte-for-byte.

Matched **before** any extension-based handler so a regex key on a
``.toml`` file uses regex semantics rather than dotted-path lookup.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._base import REGEX_KEY_PREFIX, FormatError


def _compile(key: str) -> re.Pattern[str]:
    pattern = key[len(REGEX_KEY_PREFIX):]
    if not pattern:
        raise FormatError(f"empty regex pattern in key: {key!r}")
    try:
        compiled = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise FormatError(
            f"invalid regex {pattern!r} in key {key!r}: {exc}"
        ) from exc
    if compiled.groups < 1:
        raise FormatError(
            f"regex {pattern!r} must contain exactly one capture "
            "group locating the version literal"
        )
    return compiled


class RegexFormat:
    name = "regex"

    def matches(self, file: Path, key: str | None) -> bool:
        return key is not None and key.startswith(REGEX_KEY_PREFIX)

    def read(self, file: Path, key: str | None) -> str:
        assert key is not None  # guaranteed by matches()
        text = file.read_text(encoding="utf-8")
        match = _compile(key).search(text)
        if not match:
            raise FormatError(f"regex {key!r} matched nothing in {file}")
        return match.group(1)

    def write(self, file: Path, key: str | None, value: str) -> None:
        assert key is not None
        text = file.read_text(encoding="utf-8")
        match = _compile(key).search(text)
        if not match:
            raise FormatError(f"regex {key!r} matched nothing in {file}")
        g_start, g_end = match.span(1)
        file.write_text(
            text[:g_start] + value + text[g_end:], encoding="utf-8"
        )
