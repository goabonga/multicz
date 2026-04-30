"""Read and write versions inside structured config files.

Supports four formats, dispatched by file extension:

* ``.toml`` via :mod:`tomlkit` — preserves comments, key order, whitespace.
* ``.yaml`` / ``.yml`` via :mod:`ruamel.yaml` — preserves comments and style.
* ``.json`` via :mod:`json` — preserves key order and detected indentation.
* anything else — treated as a plain text file holding only the version.

A ``key`` is a dotted path (``project.version``, ``image.tag``). Passing
``None`` means the whole file is one version literal.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import tomlkit
from ruamel.yaml import YAML


class WriterError(RuntimeError):
    """Raised when a value cannot be read or written."""


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
