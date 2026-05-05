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


def default_component_paths(
    manifest_dir: Path,
    *,
    paths_when_root: list[str],
) -> tuple[list[str], Path]:
    """Branch between root layout and subdirectory layout for a manifest.

    When the manifest lives at the repo root (``manifest_dir == Path(".")``),
    returns ``(paths_when_root, Path("CHANGELOG.md"))``. The caller owns
    the assembly of ``paths_when_root`` — what to include unconditionally
    vs after an existence check is ecosystem-specific (Cargo always ships
    ``src/**``, Python only when ``src/`` exists, etc.).

    When the manifest lives in a subdirectory, paths collapses to a
    single ``<dir>/**`` glob and the changelog lives inside that
    directory. ``paths_when_root`` is ignored in that branch since the
    glob covers everything below.
    """
    if manifest_dir == Path("."):
        return list(paths_when_root), Path("CHANGELOG.md")
    rel = manifest_dir.as_posix()
    return [f"{rel}/**"], Path(f"{rel}/CHANGELOG.md")
