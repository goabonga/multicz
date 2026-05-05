# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Go ecosystem discovery (``go.mod``, tag-driven)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..config import Component
from ._common import _find_manifests
from .context import DiscoveryContext, DiscoveryResult


def _read_go_module(path: Path) -> str | None:
    """Return the trailing segment of ``module …`` from a go.mod, ignoring /vN."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("module "):
            continue
        module = stripped[len("module "):].strip().strip('"')
        parts = [p for p in module.split("/") if p]
        if (
            len(parts) >= 2
            and parts[-1].startswith("v")
            and parts[-1][1:].isdigit()
        ):
            parts = parts[:-1]
        return parts[-1] if parts else None
    return None


class GoDiscovery:
    """Discover Go modules from ``go.mod`` files (tag-driven, no bump)."""

    name = "go"

    def discover(
        self, repo: Path, context: DiscoveryContext
    ) -> Iterable[DiscoveryResult]:
        for gomod_path in _find_manifests(repo, "go.mod"):
            raw_name = _read_go_module(gomod_path)
            if not raw_name:
                continue
            rel_dir = gomod_path.parent.relative_to(repo)
            if rel_dir == Path("."):
                paths = ["**/*.go", "go.mod"]
                if (repo / "go.sum").is_file():
                    paths.append("go.sum")
                if (repo / "Dockerfile").is_file():
                    paths.append("Dockerfile")
                changelog = Path("CHANGELOG.md")
            else:
                paths = [f"{rel_dir.as_posix()}/**"]
                changelog = Path(f"{rel_dir.as_posix()}/CHANGELOG.md")
            component = Component(
                paths=paths,
                bump_files=[],  # Go is tag-driven
                changelog=changelog,
            )
            yield DiscoveryResult(
                raw_name=raw_name,
                kind="go",
                suffix="go",
                component=component,
            )
