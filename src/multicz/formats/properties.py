# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Java-style ``.properties`` files: line-based ``key=value`` substitution.

Unlike TOML/YAML/JSON, dotted keys in ``.properties`` files are
**verbatim** (``a.b.c`` is one key, not three nested levels). The
handler keeps comments, blank lines, and trailing whitespace intact
when rewriting a value.

If the requested key doesn't exist, ``write`` appends it at the end
of the file (with a leading newline if the file didn't end on one).
``read`` raises :class:`.FormatError` when the key is missing.
"""

from __future__ import annotations

from pathlib import Path

from ._base import FormatError


def _read_line(text: str, key: str) -> str | None:
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped[0] in "#!":
            continue
        for sep in ("=", ":"):
            if sep in stripped:
                k, _, v = stripped.partition(sep)
                if k.strip() == key:
                    return v.strip()
                break
    return None


def _write_line(text: str, key: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped[0] in "#!":
            continue
        if "=" not in stripped:
            continue
        k = stripped.split("=", 1)[0].strip()
        if k != key:
            continue
        indent = line[: len(line) - len(line.lstrip())]
        ending = "\n" if line.endswith("\n") else ""
        lines[index] = f"{indent}{key}={value}{ending}"
        if not lines[index].endswith("\n") and index == len(lines) - 1:
            lines[index] += "\n"
        return "".join(lines)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] = lines[-1] + "\n"
    lines.append(f"{key}={value}\n")
    return "".join(lines)


class PropertiesFormat:
    name = "properties"

    def matches(self, file: Path, key: str | None) -> bool:
        return key is not None and file.suffix.lower() == ".properties"

    def read(self, file: Path, key: str | None) -> str:
        assert key is not None
        text = file.read_text(encoding="utf-8")
        result = _read_line(text, key)
        if result is None:
            raise FormatError(f"key {key!r} not found in {file}")
        return result

    def write(self, file: Path, key: str | None, value: str) -> None:
        assert key is not None
        text = file.read_text(encoding="utf-8")
        file.write_text(_write_line(text, key, value), encoding="utf-8")
