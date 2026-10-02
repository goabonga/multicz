# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""go-deps - claim Go components by their compiler-verified import
graph instead of a hand-maintained ``paths`` glob.

A Go binary's real dependency graph is whatever ``go list -deps``
says it is. A ``multicz.toml`` ``paths`` glob is whatever someone
remembered to write down. The two drift apart the moment a package
gains a new ``internal/`` import and nobody updates the glob - the
component silently stops seeing changes that should have bumped it.

This plugin implements :meth:`Plugin.affects` - the one hook that
runs *before* path matching has necessarily failed - to give a
component a second chance: if the plain-glob match misses a changed
file, ask the Go compiler's own import graph whether the file's
directory is actually a dependency of that component's binary.

It never *replaces* ``paths``; it only widens what counts as "yes,
this touches me" past what the globs already caught.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from multicz.plugins import BasePlugin

if TYPE_CHECKING:
    from multicz.plugins import OwnershipContext


class GoDepsPlugin(BasePlugin):
    """Plugin entry point registered under ``multicz.plugins``."""

    # ``name`` is required. It must match the entry-point key declared
    # in pyproject.toml AND the ``[plugins.<name>]`` section in the
    # consumer's multicz.toml.
    name = "go-deps"

    def __init__(self) -> None:
        # One ``go list`` call per (repo, package) for the lifetime of
        # this plugin instance - ``affects`` is called once per
        # component by ``changed`` and once per (component, commit) by
        # the planner, and the import graph doesn't change mid-run.
        self._dep_dirs_cache: dict[tuple[Path, str], frozenset[Path]] = {}

    def _packages(self, ctx: OwnershipContext) -> dict[str, str]:
        """``{component: go-package-import-path}`` from
        ``[plugins.go-deps.packages]``. A component missing from this
        map has nothing for this plugin to say about it."""
        return ctx.plugin_config.get("packages", {})

    def _dep_dirs(self, ctx: OwnershipContext, package: str) -> frozenset[Path]:
        """Resolved, absolute directories of every package ``package``
        imports (including itself) - empty on any failure (``go``
        missing, package doesn't build, …) so a broken toolchain
        degrades to "no opinion" rather than crashing the bump."""
        key = (ctx.repo, package)
        cached = self._dep_dirs_cache.get(key)
        if cached is not None:
            return cached
        try:
            result = subprocess.run(
                ["go", "list", "-deps", "-f", "{{.Dir}}", package],
                cwd=ctx.repo,
                capture_output=True,
                text=True,
            )
        except OSError:
            dirs = frozenset()
        else:
            dirs = (
                frozenset(
                    Path(line).resolve()
                    for line in result.stdout.splitlines()
                    if line.strip()
                )
                if result.returncode == 0
                else frozenset()
            )
        self._dep_dirs_cache[key] = dirs
        return dirs

    def affects(
        self, ctx: OwnershipContext, component: str, paths: list[str]
    ) -> bool:
        package = self._packages(ctx).get(component)
        if package is None:
            return False
        dep_dirs = self._dep_dirs(ctx, package)
        if not dep_dirs:
            return False
        return any(
            (ctx.repo / path).resolve().parent in dep_dirs for path in paths
        )
