# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Source-loading layer for the multicz config.

The schema (``models.py``) is independent of *where* the config text
comes from. This module owns that I/O concern: a small ``ConfigSource``
Protocol plus one implementation per host file (``multicz.toml``,
``pyproject.toml`` ``[tool.multicz]``, ``package.json`` ``"multicz"``
key), wired together by ``load_config`` and ``find_config``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import tomlkit

from .models import Config

CONFIG_FILENAME = "multicz.toml"


class ConfigSource(Protocol):
    """Read a raw multicz config dict from a specific host file."""

    name: str
    filename: str

    def extract(self, file: Path) -> dict[str, Any] | None:
        """Return the multicz config dict embedded in ``file``, or ``None``.

        ``None`` means "the file exists but doesn't carry multicz
        config", which lets ``find_config`` skip it and keep walking.
        """
        ...


def _read_text(file: Path) -> str | None:
    try:
        return file.read_text(encoding="utf-8")
    except OSError:
        return None


class MulticzTomlSource:
    """Whole-file source: ``multicz.toml`` IS the multicz config."""

    name = "multicz-toml"
    filename = CONFIG_FILENAME

    def extract(self, file: Path) -> dict[str, Any] | None:
        text = _read_text(file)
        if text is None:
            return None
        try:
            return tomlkit.parse(text).unwrap()
        except Exception:
            return None


class PyprojectSource:
    """``pyproject.toml`` source: reads the ``[tool.multicz]`` table."""

    name = "pyproject"
    filename = "pyproject.toml"

    def extract(self, file: Path) -> dict[str, Any] | None:
        text = _read_text(file)
        if text is None:
            return None
        try:
            doc = tomlkit.parse(text).unwrap()
        except Exception:
            return None
        tool = doc.get("tool")
        if isinstance(tool, dict):
            section = tool.get("multicz")
            if isinstance(section, dict):
                return section
        return None


class PackageJsonSource:
    """``package.json`` source: reads the top-level ``"multicz"`` key."""

    name = "package-json"
    filename = "package.json"

    def extract(self, file: Path) -> dict[str, Any] | None:
        text = _read_text(file)
        if text is None:
            return None
        try:
            data = json.loads(text)
        except Exception:
            return None
        section = data.get("multicz") if isinstance(data, dict) else None
        return section if isinstance(section, dict) else None


CONFIG_SOURCES: list[ConfigSource] = [
    MulticzTomlSource(),
    PyprojectSource(),
    PackageJsonSource(),
]


def _source_for(file: Path) -> ConfigSource | None:
    """Find the source whose filename matches ``file.name``."""
    for src in CONFIG_SOURCES:
        if src.filename == file.name:
            return src
    return None


def load_config(path: Path) -> Config:
    """Load and validate a multicz config from ``path``.

    Accepts ``multicz.toml`` (whole-file), ``pyproject.toml``
    (``[tool.multicz]``), or ``package.json`` (``"multicz"`` key).
    """
    src = _source_for(path)
    raw = src.extract(path) if src is not None else None
    if raw is None:
        raise FileNotFoundError(f"no multicz config found in {path}")
    config = Config.model_validate(raw)
    config.validate_references()
    return config


def find_config(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: cwd) looking for a multicz config.

    At each directory level, the search order is:

    1. ``multicz.toml`` (always wins when present),
    2. ``pyproject.toml`` with a ``[tool.multicz]`` table,
    3. ``package.json`` with a top-level ``"multicz"`` key.
    """
    here = (start or Path.cwd()).resolve()
    canonical = CONFIG_SOURCES[0]
    fallbacks = CONFIG_SOURCES[1:]
    for directory in (here, *here.parents):
        canonical_path = directory / canonical.filename
        if canonical_path.is_file():
            return canonical_path
        for src in fallbacks:
            candidate = directory / src.filename
            if candidate.is_file() and src.extract(candidate) is not None:
                return candidate
    raise FileNotFoundError(
        "no multicz config found (looked for multicz.toml, "
        "pyproject.toml [tool.multicz], or package.json \"multicz\" key) "
        f"in {here} or any parent directory"
    )
