# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Rust/Cargo ecosystem discovery (``Cargo.toml`` + workspace excludes)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import tomlkit

from ..config import Component, FileKey
from ._common import _find_manifests
from .context import DiscoveryContext, DiscoveryResult


def _read_cargo_excludes(repo: Path) -> set[Path]:
    """Resolve ``[workspace].exclude`` paths from a root Cargo.toml.

    Each entry is a directory path (not a glob). The contained
    ``Cargo.toml`` is what we want to skip during discovery.
    """
    root = repo / "Cargo.toml"
    if not root.is_file():
        return set()
    try:
        doc = tomlkit.parse(root.read_text(encoding="utf-8"))
    except Exception:
        return set()
    workspace = doc.get("workspace")
    if not isinstance(workspace, dict):
        return set()
    excludes = workspace.get("exclude")
    if not isinstance(excludes, list):
        return set()
    out: set[Path] = set()
    for entry in excludes:
        if not isinstance(entry, str):
            continue
        candidate = (repo / entry / "Cargo.toml")
        if candidate.is_file():
            out.add(candidate.resolve())
    return out


def _read_cargo(path: Path) -> tuple[str | None, str] | None:
    """Read a Cargo.toml. Returns (name, version_key) or None when there's
    nothing to bump (e.g. a workspace-only file with no shared version, or
    a member crate that inherits via ``version.workspace = true``).
    """
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    workspace = doc.get("workspace")
    if isinstance(workspace, dict):
        wpkg = workspace.get("package")
        if isinstance(wpkg, dict) and "version" in wpkg:
            name: str | None = None
            pkg = doc.get("package")
            if isinstance(pkg, dict):
                pkg_name = pkg.get("name")
                if pkg_name:
                    name = str(pkg_name)
            return (name, "workspace.package.version")

    pkg = doc.get("package")
    if not isinstance(pkg, dict):
        return None
    pkg_version = pkg.get("version")
    if pkg_version is None or isinstance(pkg_version, dict):
        # missing or inheriting from workspace
        return None
    pkg_name = pkg.get("name")
    if not pkg_name:
        return None
    return (str(pkg_name), "package.version")


class CargoDiscovery:
    """Discover Rust crates from ``Cargo.toml`` manifests."""

    name = "cargo"

    def discover(
        self, repo: Path, context: DiscoveryContext
    ) -> Iterable[DiscoveryResult]:
        cargo_excluded = _read_cargo_excludes(repo)
        for cargo_path in _find_manifests(repo, "Cargo.toml"):
            if cargo_path.resolve() in cargo_excluded:
                continue
            info = _read_cargo(cargo_path)
            if info is None:
                continue
            raw_name, version_key = info
            if not raw_name:
                continue
            rel_dir = cargo_path.parent.relative_to(repo)
            if rel_dir == Path("."):
                paths = ["src/**", "Cargo.toml"]
                if (repo / "Cargo.lock").is_file():
                    paths.append("Cargo.lock")
                if (repo / "tests").is_dir():
                    paths.append("tests/**")
                if (repo / "Dockerfile").is_file():
                    paths.append("Dockerfile")
                changelog = Path("CHANGELOG.md")
            else:
                paths = [f"{rel_dir.as_posix()}/**"]
                changelog = Path(f"{rel_dir.as_posix()}/CHANGELOG.md")
            component = Component(
                paths=paths,
                bump_files=[FileKey(file=cargo_path.relative_to(repo), key=version_key)],
                changelog=changelog,
            )
            yield DiscoveryResult(
                raw_name=raw_name,
                kind="cargo",
                suffix="crate",
                component=component,
            )
