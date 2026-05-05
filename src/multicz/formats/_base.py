# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Core protocol every file format implements.

multicz reads / writes a single string value at a key inside many
flavours of structured config file (TOML, YAML, JSON, .properties,
plain text, regex-anchored). Every flavour is a class implementing
:class:`FileFormat`. The package's :data:`FORMATS` registry orders
them so the first one whose ``matches()`` returns ``True`` claims the
read/write operation; format files don't know about each other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

REGEX_KEY_PREFIX = "regex:"


class FormatError(RuntimeError):
    """Raised when a value cannot be read or written."""


class FileFormat(Protocol):
    """Read and write a version-bearing value inside a structured file.

    Implementations are stateless — instances are created once at
    module load time and reused. ``matches`` is the dispatcher entry
    point: order in :data:`.FORMATS` resolves any ambiguity between
    handlers that could in principle both claim the same file.
    """

    name: str

    def matches(self, file: Path, key: str | None) -> bool:
        """Return ``True`` if this handler should process ``(file, key)``."""
        ...

    def read(self, file: Path, key: str | None) -> str:
        """Return the current value at ``key`` in ``file``."""
        ...

    def write(self, file: Path, key: str | None, value: str) -> None:
        """Write ``value`` at ``key`` in ``file``, preserving the rest."""
        ...
