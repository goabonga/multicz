# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Helpers shared by more than one discovery strategy.

Anything ecosystem-specific lives in the per-ecosystem module
(:mod:`.python`, :mod:`.cargo`, ...). This module only carries the
manifest-walking primitive and the noise-directory list it consults,
both of which are used by every file-walking strategy.
"""

from __future__ import annotations

from pathlib import Path

# Directories never recursed into when scanning for manifests.
_NOISE_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", ".venv", "venv", ".tox", ".nox",
    "vendor", "third_party",
    "target", "build", "dist",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
})


def _find_manifests(repo: Path, filename: str) -> list[Path]:
    """Return every ``filename`` under ``repo`` outside noise dirs."""
    found: list[Path] = []
    for path in repo.rglob(filename):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo).parts
        if any(part in _NOISE_DIRS for part in rel_parts):
            continue
        found.append(path)
    return sorted(found)
