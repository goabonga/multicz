# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Python ecosystem discovery (``pyproject.toml`` + uv workspace)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import tomlkit

from ..config import Component, FileKey
from ._common import _find_manifests, default_component_paths
from .context import DiscoveryContext, DiscoveryResult


def _read_pyproject_info(path: Path) -> tuple[str, str] | None:
    """Return ``(name, version_key)`` for a Python project, or ``None``.

    Handles both PEP 621 (``[project]``, used by uv/hatch/setuptools-pep621
    and modern Poetry) and legacy Poetry (``[tool.poetry]``). Files that
    declare neither are typically uv workspace orchestrators and are
    skipped (returning ``None``).
    """
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    project = doc.get("project")
    if isinstance(project, dict):
        name = project.get("name")
        if name and "version" in project:
            return (str(name), "project.version")

    tool = doc.get("tool")
    if isinstance(tool, dict):
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            name = poetry.get("name")
            version = poetry.get("version")
            if name and version is not None:
                return (str(name), "tool.poetry.version")

    return None


def _read_uv_workspace(path: Path) -> tuple[list[str], list[str]]:
    """Return ``(members_globs, exclude_globs)`` from ``[tool.uv.workspace]``."""
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return [], []
    tool = doc.get("tool")
    if not isinstance(tool, dict):
        return [], []
    uv = tool.get("uv")
    if not isinstance(uv, dict):
        return [], []
    workspace = uv.get("workspace")
    if not isinstance(workspace, dict):
        return [], []

    def _list(value) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value if isinstance(v, str)]
        return []

    return _list(workspace.get("members")), _list(workspace.get("exclude"))


class PythonDiscovery:
    """Discover Python projects from ``pyproject.toml`` files.

    Walks every ``pyproject.toml`` under the repo, honours
    ``[tool.uv.workspace].exclude``, and emits one component per
    declared project.
    """

    name = "python"

    def discover(
        self, repo: Path, context: DiscoveryContext
    ) -> Iterable[DiscoveryResult]:
        pyprojects = _find_manifests(repo, "pyproject.toml")
        excluded: set[Path] = set()
        root_pyproject = repo / "pyproject.toml"
        if root_pyproject.is_file():
            _, ws_excludes = _read_uv_workspace(root_pyproject)
            for pattern in ws_excludes:
                for path in repo.glob(f"{pattern}/pyproject.toml"):
                    excluded.add(path.resolve())

        for path in pyprojects:
            if path.resolve() in excluded:
                continue
            info = _read_pyproject_info(path)
            if info is None:
                continue  # uv workspace orchestrator with no [project], skip
            raw_name, version_key = info
            rel_dir = path.parent.relative_to(repo)
            root_paths = ["pyproject.toml"]
            if (repo / "src").is_dir():
                root_paths.insert(0, "src/**")
            if (repo / "tests").is_dir():
                root_paths.append("tests/**")
            if (repo / "Dockerfile").is_file():
                root_paths.append("Dockerfile")
            paths, changelog = default_component_paths(
                rel_dir, paths_when_root=root_paths,
            )
            component = Component(
                paths=paths,
                bump_files=[FileKey(file=path.relative_to(repo), key=version_key)],
                changelog=changelog,
            )
            yield DiscoveryResult(
                raw_name=raw_name,
                kind="python",
                suffix="py",
                component=component,
            )
