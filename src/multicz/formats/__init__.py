# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Read and write versions inside structured config files.

Each supported format is a small class implementing :class:`FileFormat`
(see :mod:`._base`); the registry below orders them so the **first**
one whose ``matches()`` returns ``True`` claims the operation.

Order matters — `regex` and `plain` come before extension-based
handlers so a ``regex:...`` key on a ``.toml`` file uses regex
semantics and a ``key=None`` on a ``.json`` file is treated as a plain
single-value file rather than a structured one.

Adding a new format is one new module + one entry in :data:`FORMATS`.
"""

from __future__ import annotations

from pathlib import Path

from ._base import REGEX_KEY_PREFIX, FileFormat, FormatError
from .json import JsonFormat
from .plain import PlainFormat
from .properties import PropertiesFormat
from .regex import RegexFormat
from .toml import TomlFormat
from .yaml import YamlFormat

FORMATS: list[FileFormat] = [
    RegexFormat(),
    PlainFormat(),
    PropertiesFormat(),
    TomlFormat(),
    YamlFormat(),
    JsonFormat(),
]


__all__ = [
    "FORMATS",
    "REGEX_KEY_PREFIX",
    "FileFormat",
    "FormatError",
    "JsonFormat",
    "PlainFormat",
    "PropertiesFormat",
    "RegexFormat",
    "TomlFormat",
    "YamlFormat",
    "read_value",
    "write_value",
]


def _select(file: Path, key: str | None) -> FileFormat:
    for fmt in FORMATS:
        if fmt.matches(file, key):
            return fmt
    raise FormatError(
        f"no format handler claimed {file} (key={key!r}); "
        f"plain-file values cannot have a key"
    )


def read_value(file: Path, key: str | None) -> str:
    """Return the version literal at ``key`` in ``file``."""
    return _select(file, key).read(file, key)


def write_value(file: Path, key: str | None, value: str) -> None:
    """Write ``value`` at ``key`` in ``file``, preserving everything else.

    Raises :class:`FormatError` if the file doesn't exist; format
    handlers themselves raise on missing keys, invalid regexes, or
    when a plain-file key isn't ``None``.
    """
    if not file.exists():
        raise FormatError(f"file does not exist: {file}")
    _select(file, key).write(file, key, value)
