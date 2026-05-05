# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Node.js ecosystem discovery (``package.json`` + workspaces).

Currently exposed as a post-pass free function (:func:`_detect_node`)
rather than a regular discovery strategy because it needs to know
whether a Python component already claimed the root in order to
decide whether to add ``src/**`` and ``CHANGELOG.md`` to a root
``package.json``. Stage 4 will move this behind a relation/strategy
protocol.
"""

from __future__ import annotations

import json
from pathlib import Path

from ruamel.yaml import YAML

from ..config import Component, FileKey
from ._common import _NOISE_DIRS, _find_manifests, default_component_paths
from .context import DiscoveryContext


def _read_package_json_name(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    name = data.get("name")
    if not name:
        return None
    # npm scopes (@scope/pkg) are not valid TOML table keys without quoting and
    # produce ugly tags; prefer the unscoped portion.
    return str(name).split("/", 1)[-1]


def _read_package_json_version(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data.get("version") if isinstance(data, dict) else None


def _read_workspace_globs(
    package_json: Path, pnpm_workspace: Path
) -> list[str]:
    """Return workspace member globs from npm/yarn (package.json) or pnpm.

    Recognised shapes:

    * ``"workspaces": ["packages/*"]`` (npm, yarn classic)
    * ``"workspaces": {"packages": ["packages/*"]}`` (yarn berry)
    * ``pnpm-workspace.yaml`` with ``packages: [...]``
    """
    globs: list[str] = []
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict):
            workspaces = data.get("workspaces")
            if isinstance(workspaces, list):
                globs = [str(g) for g in workspaces if isinstance(g, str)]
            elif isinstance(workspaces, dict):
                packages = workspaces.get("packages")
                if isinstance(packages, list):
                    globs = [str(g) for g in packages if isinstance(g, str)]
    if not globs and pnpm_workspace.is_file():
        try:
            data = YAML(typ="safe").load(
                pnpm_workspace.read_text(encoding="utf-8")
            ) or {}
        except Exception:
            data = {}
        packages = data.get("packages") if isinstance(data, dict) else None
        if isinstance(packages, list):
            globs = [str(g) for g in packages if isinstance(g, str)]
    return globs


def _detect_node(
    repo: Path,
    components: dict[str, Component],
    context: DiscoveryContext,
) -> None:
    """Add Node.js components, expanding workspaces when declared.

    When the repo declares a workspace (npm/yarn ``"workspaces"`` array,
    yarn-berry ``"workspaces.packages"``, or ``pnpm-workspace.yaml``), only
    the listed members are added - the user has been explicit about what
    is and isn't part of the workspace.

    When no workspace is declared, every ``package.json`` outside noise dirs
    is added as its own component. That covers the common FastAPI + React
    layout where the SPA sits in ``frontend/`` next to a root pyproject.
    """
    python_taken = bool(context.by_kind("python"))
    root_pkg = repo / "package.json"
    pnpm_ws = repo / "pnpm-workspace.yaml"
    workspace_globs = _read_workspace_globs(root_pkg, pnpm_ws)

    # npm/yarn/pnpm support '!pattern' to exclude members from a workspace.
    include_globs = [g for g in workspace_globs if not g.startswith("!")]
    exclude_globs = [g[1:] for g in workspace_globs if g.startswith("!")]

    candidates: list[Path] = []
    if include_globs:
        excluded_paths: set[Path] = set()
        for pattern in exclude_globs:
            for member in repo.glob(f"{pattern}/package.json"):
                excluded_paths.add(member.resolve())
        for pattern in include_globs:
            for member in sorted(repo.glob(f"{pattern}/package.json")):
                if any(
                    part in _NOISE_DIRS for part in member.relative_to(repo).parts
                ):
                    continue
                if member.resolve() in excluded_paths:
                    continue
                candidates.append(member)
    elif workspace_globs:
        # globs were declared but they're all '!exclusions' with no includes -
        # nothing to add.
        return
    else:
        candidates = _find_manifests(repo, "package.json")

    for path in candidates:
        name = _read_package_json_name(path)
        version = _read_package_json_version(path)
        if not name or version is None:
            continue
        comp_name = _node_unique(name, set(components))
        rel_dir = path.parent.relative_to(repo)
        root_paths = ["package.json"]
        if not python_taken and (repo / "src").is_dir():
            root_paths.insert(0, "src/**")
        paths, _changelog = default_component_paths(
            rel_dir, paths_when_root=root_paths,
        )
        # When a Python component already owns the root CHANGELOG.md,
        # the JS root component leaves changelog unset to avoid a
        # second component clobbering the same file.
        changelog: Path | None = (
            None if rel_dir == Path(".") and python_taken else _changelog
        )
        components[comp_name] = Component(
            paths=paths,
            bump_files=[FileKey(file=path.relative_to(repo), key="version")],
            changelog=changelog,
        )


def _node_unique(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    candidate = f"{name}-js"
    counter = 2
    while candidate in taken:
        candidate = f"{name}-js-{counter}"
        counter += 1
    return candidate
