# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""YAML handler — preserves comments and quoting via :mod:`ruamel.yaml`.

Configured with ``typ="rt"`` (round-trip), ``preserve_quotes=True``,
and a ``mapping=2 / sequence=4 / offset=2`` indent — matches Helm's
default Chart.yaml style and most hand-written YAML configs.
"""

from __future__ import annotations

import io
from pathlib import Path

from ruamel.yaml import YAML

from ._base import FormatError
from ._common import navigate, split_key


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


class YamlFormat:
    name = "yaml"

    def matches(self, file: Path, key: str | None) -> bool:
        return key is not None and file.suffix.lower() in {".yaml", ".yml"}

    def read(self, file: Path, key: str | None) -> str:
        assert key is not None
        parts = split_key(key)
        data = _yaml().load(io.StringIO(file.read_text(encoding="utf-8"))) or {}
        cursor, last = navigate(data, parts, create=False)
        if last not in cursor:
            raise FormatError(f"key {key!r} not found in {file}")
        return str(cursor[last])

    def write(self, file: Path, key: str | None, value: str) -> None:
        assert key is not None
        parts = split_key(key)
        yaml = _yaml()
        data = yaml.load(file.read_text(encoding="utf-8")) or {}
        cursor, last = navigate(data, parts, create=True)
        cursor[last] = value
        buffer = io.StringIO()
        yaml.dump(data, buffer)
        file.write_text(buffer.getvalue(), encoding="utf-8")
