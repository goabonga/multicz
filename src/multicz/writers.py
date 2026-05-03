# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Read and write versions inside structured config files.

Supports five formats, dispatched by file extension:

* ``.toml`` via :mod:`tomlkit` — preserves comments, key order, whitespace.
* ``.yaml`` / ``.yml`` via :mod:`ruamel.yaml` — preserves comments and style.
* ``.json`` via :mod:`json` — preserves key order and detected indentation.
* ``.properties`` — line-based key=value substitution, preserves comments.
* anything else — treated as a plain text file holding only the version.

A ``key`` is a dotted path (``project.version``, ``image.tag``). Passing
``None`` means the whole file is one version literal. For ``.properties``
files the dotted-path interpretation is disabled — the key is taken
verbatim, since properties files routinely use dotted keys (``a.b.c``)
that are *not* nested.

A ``key`` prefixed with ``regex:`` is a language-agnostic escape hatch:
the rest of the string is a regex with one capture group locating the
version literal. Useful for ``__version__ = "X"`` in Python,
``export const VERSION = "X"`` in TypeScript, ``VERSION := X`` in
Makefiles, etc. The regex is anchored with :data:`re.MULTILINE`, and
only the *first* match's capture group is rewritten.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import tomlkit
from ruamel.yaml import YAML

REGEX_KEY_PREFIX = "regex:"


class WriterError(RuntimeError):
    """Raised when a value cannot be read or written."""


def _is_regex_key(key: str | None) -> bool:
    return key is not None and key.startswith(REGEX_KEY_PREFIX)


def _compile_regex_key(key: str) -> re.Pattern[str]:
    pattern = key[len(REGEX_KEY_PREFIX):]
    if not pattern:
        raise WriterError(f"empty regex pattern in key: {key!r}")
    try:
        compiled = re.compile(pattern, re.MULTILINE)
    except re.error as exc:
        raise WriterError(
            f"invalid regex {pattern!r} in key {key!r}: {exc}"
        ) from exc
    if compiled.groups < 1:
        raise WriterError(
            f"regex {pattern!r} must contain exactly one capture "
            "group locating the version literal"
        )
    return compiled


def _split_key(key: str) -> list[str]:
    parts = [part for part in key.split(".") if part]
    if not parts:
        raise WriterError(f"empty key: {key!r}")
    return parts


def _navigate(root, parts: list[str], create: bool):
    """Walk ``root`` via ``parts`` returning ``(parent, last_part)``."""
    cursor = root
    for part in parts[:-1]:
        if part not in cursor:
            if not create:
                raise WriterError(f"missing key {part!r} while reading")
            cursor[part] = {}
        cursor = cursor[part]
    return cursor, parts[-1]


def _is_toml(file: Path) -> bool:
    return file.suffix.lower() == ".toml"


def _is_yaml(file: Path) -> bool:
    return file.suffix.lower() in {".yaml", ".yml"}


def _is_json(file: Path) -> bool:
    return file.suffix.lower() == ".json"


def _is_properties(file: Path) -> bool:
    return file.suffix.lower() == ".properties"


def _read_property(text: str, key: str) -> str | None:
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


def _write_property(text: str, key: str, value: str) -> str:
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


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def _detect_json_indent(text: str) -> int:
    """Best-effort indent detection: width of the first indented line."""
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        if stripped and stripped != line:
            return len(line) - len(stripped)
    return 2


def read_value(file: Path, key: str | None) -> str:
    text = file.read_text(encoding="utf-8")
    if key is None:
        return text.strip()
    if _is_regex_key(key):
        pattern = _compile_regex_key(key)
        match = pattern.search(text)
        if not match:
            raise WriterError(
                f"regex {key!r} matched nothing in {file}"
            )
        return match.group(1)
    if _is_properties(file):
        result = _read_property(text, key)
        if result is None:
            raise WriterError(f"key {key!r} not found in {file}")
        return result
    parts = _split_key(key)
    if _is_toml(file):
        doc = tomlkit.parse(text)
        cursor, last = _navigate(doc, parts, create=False)
        if last not in cursor:
            raise WriterError(f"key {key!r} not found in {file}")
        return str(cursor[last])
    if _is_yaml(file):
        data = _yaml().load(io.StringIO(text)) or {}
        cursor, last = _navigate(data, parts, create=False)
        if last not in cursor:
            raise WriterError(f"key {key!r} not found in {file}")
        return str(cursor[last])
    if _is_json(file):
        data = json.loads(text or "{}")
        cursor, last = _navigate(data, parts, create=False)
        if last not in cursor:
            raise WriterError(f"key {key!r} not found in {file}")
        return str(cursor[last])
    raise WriterError(
        f"plain-file values cannot have a key (got {key!r} for {file.name})"
    )


def write_value(file: Path, key: str | None, value: str) -> None:
    if not file.exists():
        raise WriterError(f"file does not exist: {file}")
    if key is None:
        file.write_text(value + "\n", encoding="utf-8")
        return

    if _is_regex_key(key):
        pattern = _compile_regex_key(key)
        text = file.read_text(encoding="utf-8")
        match = pattern.search(text)
        if not match:
            raise WriterError(
                f"regex {key!r} matched nothing in {file}"
            )
        # Replace only the first match's capture group, preserving the
        # surrounding text byte-for-byte (quotes, indentation, comments).
        g_start, g_end = match.span(1)
        file.write_text(
            text[:g_start] + value + text[g_end:], encoding="utf-8"
        )
        return

    if _is_properties(file):
        text = file.read_text(encoding="utf-8")
        file.write_text(_write_property(text, key, value), encoding="utf-8")
        return

    parts = _split_key(key)
    if _is_toml(file):
        doc = tomlkit.parse(file.read_text(encoding="utf-8"))
        cursor, last = _navigate(doc, parts, create=True)
        cursor[last] = value
        file.write_text(tomlkit.dumps(doc), encoding="utf-8")
        return
    if _is_yaml(file):
        yaml = _yaml()
        data = yaml.load(file.read_text(encoding="utf-8")) or {}
        cursor, last = _navigate(data, parts, create=True)
        cursor[last] = value
        buffer = io.StringIO()
        yaml.dump(data, buffer)
        file.write_text(buffer.getvalue(), encoding="utf-8")
        return
    if _is_json(file):
        text = file.read_text(encoding="utf-8")
        indent = _detect_json_indent(text)
        data = json.loads(text or "{}")
        cursor, last = _navigate(data, parts, create=True)
        cursor[last] = value
        rendered = json.dumps(data, indent=indent, ensure_ascii=False)
        file.write_text(rendered + "\n", encoding="utf-8")
        return
    raise WriterError(
        f"plain-file values cannot have a key (got {key!r} for {file.name})"
    )
