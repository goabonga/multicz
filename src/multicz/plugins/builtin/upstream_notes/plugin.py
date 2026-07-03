# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Upstream-notes plugin.

Injects the *commits* of upstream components (not just their version)
into a downstream component's changelog / release notes.

Typical Terraform layout::

    module  --(depends_on)-->  root  --(deploy pipeline)-->  config-*

When ``config-prod`` bumps (e.g. via a ``deploy`` commit created by the
apply pipeline), its notes normally only contain that deploy commit.
This plugin adds one section per upstream::

    ### Upstream: root (v1.3.0 → v1.4.0)
    - feat(network): add private endpoint subnet (a1b2c3d)
    ### Upstream: module (v0.9.1 → v0.9.2)
    - fix: pin azurerm provider (d4e5f6a)

Baseline resolution
-------------------
For each upstream, the "previous" version is the highest upstream tag
**merged into the component's previously released tag** (``git tag
--merged <comp-prev-tag>``). The "new" version is the latest upstream
tag reachable from HEAD. This works even when the deploy commit lands
*after* the upstream release commit (separate pipeline run): everything
tagged upstream since the last config release is, by construction, what
this deployment ships.

Configuration (multicz.toml)::

    [plugins.upstream-notes]
    max_commits = 30          # per upstream section, default 30
    include_prereleases = false

    # Explicit mapping. When absent, falls back to the transitive
    # closure of each component's ``depends_on``.
    [plugins.upstream-notes.upstreams]
    config-prod = ["root", "module"]
    config-staging = ["root", "module"]
"""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING

from packaging.version import InvalidVersion, Version

from multicz.commits import (
    commits_in_range,
    latest_stable_tag,
    latest_tag,
    tag_prefix,
)
from multicz.config import ComponentMatcher

from ...protocol import BasePlugin, ChangelogEntry

if TYPE_CHECKING:
    from pathlib import Path

    from ...protocol import PluginContext


def _git(args: list[str], cwd: Path) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    return out.stdout if out.returncode == 0 else ""


def _highest_tag_merged(repo: Path, prefix: str, ref: str) -> str | None:
    """Highest version tag starting with ``prefix`` merged into ``ref``."""
    out = _git(["tag", "--merged", ref, "--list", f"{prefix}*"], repo)
    best: tuple[Version, str] | None = None
    for line in out.splitlines():
        name = line.strip()
        if not name.startswith(prefix):
            continue
        try:
            v = Version(name[len(prefix):])
        except InvalidVersion:
            continue
        if best is None or v > best[0]:
            best = (v, name)
    return best[1] if best else None


def _tag_exists(repo: Path, tag: str) -> bool:
    return bool(_git(["rev-parse", "--verify", f"refs/tags/{tag}"], repo).strip())


class UpstreamNotesPlugin(BasePlugin):
    """Built-in upstream-notes plugin — see the module docstring."""

    name = "upstream-notes"

    # ------------------------------------------------------------------
    # upstream resolution
    # ------------------------------------------------------------------
    def _upstreams_for(self, ctx: PluginContext, component: str) -> list[str]:
        """Explicit config mapping first, otherwise the transitive
        closure of ``depends_on`` (root pulls in module, etc.)."""
        mapping = ctx.plugin_config.get("upstreams", {}) or {}
        explicit = mapping.get(component)
        if explicit:
            return [u for u in explicit if u in ctx.config.components]

        seen: list[str] = []
        stack = list(ctx.config.components[component].depends_on)
        while stack:
            up = stack.pop(0)
            if up in seen or up == component or up not in ctx.config.components:
                continue
            seen.append(up)
            stack.extend(ctx.config.components[up].depends_on)
        return seen

    # ------------------------------------------------------------------
    # hooks
    # ------------------------------------------------------------------
    def enrich_changelog(
        self, ctx: PluginContext, component: str
    ) -> list[ChangelogEntry]:
        bump = ctx.plan.bumps.get(component)
        if bump is None:
            return []

        upstreams = self._upstreams_for(ctx, component)
        if not upstreams:
            return []

        max_commits = int(ctx.plugin_config.get("max_commits", 30))
        include_pre = bool(ctx.plugin_config.get("include_prereleases", False))
        matcher = ComponentMatcher(ctx.config.components)
        release_re = re.compile(ctx.config.project.release_commit_pattern)

        # Baseline = the component's currently released tag (pre-bump).
        comp_prefix = tag_prefix(ctx.config.tag_format_for(component), component)
        baseline: str | None = f"{comp_prefix}{bump.current}"
        if not _tag_exists(ctx.repo, baseline):
            baseline = None  # first release: diff upstream against nothing

        entries: list[ChangelogEntry] = []
        for upstream in upstreams:
            up_prefix = tag_prefix(ctx.config.tag_format_for(upstream), upstream)

            head_tag = (
                latest_tag(ctx.repo, up_prefix)
                if include_pre
                else latest_stable_tag(ctx.repo, up_prefix)
            )
            if head_tag is None:
                continue

            prev_tag = (
                _highest_tag_merged(ctx.repo, up_prefix, baseline)
                if baseline
                else None
            )
            if prev_tag == head_tag:
                continue  # upstream unchanged since last release of `component`

            ignored = ctx.config.ignored_types_for(upstream)
            commits = [
                c
                for c in commits_in_range(ctx.repo, prev_tag, head_tag)
                if c.is_conventional
                and c.type.lower() not in ignored
                and not release_re.match(
                    f"{c.type}({c.scope}): {c.subject}" if c.scope
                    else f"{c.type}: {c.subject}"
                )
                and any(matcher.match(f) == upstream for f in c.files)
            ]
            if not commits:
                continue

            lines: list[str] = []
            for c in commits[:max_commits]:
                scope = f"({c.scope})" if c.scope else ""
                bang = "!" if c.breaking else ""
                lines.append(f"- {c.type}{scope}{bang}: {c.subject} ({c.sha[:7]})")
            if len(commits) > max_commits:
                lines.append(f"- … and {len(commits) - max_commits} more")

            prev_label = prev_tag[len(up_prefix):] if prev_tag else "∅"
            head_label = head_tag[len(up_prefix):]
            entries.append(
                ChangelogEntry(
                    section=f"Upstream: {upstream} (v{prev_label} → v{head_label})",
                    component=component,
                    lines=tuple(lines),
                )
            )
        return entries

    # ------------------------------------------------------------------
    # bonus: surface pending upstream drift in ``multicz status`` / ``plan``
    # ------------------------------------------------------------------
    def status_lines(self, ctx: PluginContext) -> list[str]:
        lines: list[str] = []
        for component in ctx.plan.bumps:
            for entry in self.enrich_changelog(ctx, component):
                lines.append(
                    f"{component}: ships {len(entry.lines)} upstream change(s) "
                    f"\\[{entry.section}]"
                )
        return lines
