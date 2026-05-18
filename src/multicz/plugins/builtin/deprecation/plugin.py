# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Deprecation-policy plugin.

Reads its config from ``[plugins.deprecation]`` in multicz.toml::

    [plugins.deprecation]
    enabled = true
    # Globs (one per component, or shared) — relative to repo root.
    # When omitted, defaults to each component's `paths`.
    scan = ["packages/api/src/**/*.py", "packages/api/**/*.toml"]
    # Severity for the "must be removed" violation: "error" (default)
    # aborts the bump, "warning" only informs.
    mode = "error"

Behaviour:

* On every ``post_plan`` invocation, scan the configured paths (or, by
  default, each component's :attr:`Component.paths`).
* For every marker whose ``remove_in`` ≤ the planned ``next`` version,
  emit a :class:`Violation` so the bump aborts (or warns) until the
  caller actually removes the deprecated code.
* Contribute ``Deprecated`` + ``Removed`` sections to the changelog /
  release notes via :meth:`Plugin.enrich_changelog`.
* Surface a pre-flight summary in ``multicz status`` /
  ``multicz plan`` via :meth:`Plugin.status_lines`.

Activation is **explicit opt-in**: even though multicz ships the
plugin via its own entry point, it only runs when the project
declares ``[plugins.deprecation]`` in its multicz.toml (an empty
section is fine — it means "use all defaults"). Without that
section the plugin is shown as ``inactive`` in ``multicz plugins``
and never gates a bump. To temporarily disable an already-declared
section, set ``enabled = false`` under it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from packaging.version import Version

from ...protocol import (
    BasePlugin,
    ChangelogEntry,
    PluginContext,
    Severity,
    Violation,
)
from .scanner import Deprecation, scan_paths

if TYPE_CHECKING:
    from ....planner import PlannedBump


class DeprecationPlugin(BasePlugin):
    """Built-in deprecation-policy enforcer.

    Tied to the ``[plugins.deprecation]`` config section; opt-out via
    ``enabled = false``.
    """

    name = "deprecation"

    # ------------------------------------------------------------------
    # Config parsing helpers
    # ------------------------------------------------------------------

    def _enabled(self, ctx: PluginContext) -> bool:
        return bool(ctx.plugin_config.get("enabled", True))

    def _mode(self, ctx: PluginContext) -> Severity:
        raw = ctx.plugin_config.get("mode", "error")
        try:
            return Severity(raw)
        except ValueError:
            return Severity.error

    def _scan_globs_for(
        self, ctx: PluginContext, component_name: str
    ) -> list[str]:
        """Resolve the scan globs for one component.

        Priority:
        1. ``[plugins.deprecation.scan."<component>"] = [...]`` —
           per-component override.
        2. ``[plugins.deprecation].scan = [...]`` — global glob list.
        3. The component's own ``paths`` (fall-back, lets the plugin
           work zero-config on any well-formed multicz repo).
        """
        per_component = ctx.plugin_config.get("scan_per_component", {})
        if isinstance(per_component, dict) and component_name in per_component:
            return list(per_component[component_name])
        shared = ctx.plugin_config.get("scan")
        if shared:
            return list(shared)
        component = ctx.config.components.get(component_name)
        if component is None:
            return []
        return [str(p) for p in component.paths]

    def _scan_component(self, ctx: PluginContext, component_name: str) -> list[Deprecation]:
        globs = self._scan_globs_for(ctx, component_name)
        return scan_paths(ctx.repo, globs)

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def post_plan(self, ctx: PluginContext) -> list[Violation]:
        if not self._enabled(ctx):
            return []
        mode = self._mode(ctx)
        violations: list[Violation] = []
        for planned in ctx.plan:
            next_v = Version(planned.next)
            for dep in self._scan_component(ctx, planned.component):
                if dep.remove_in <= next_v:
                    suffix = f" — {dep.message}" if dep.message else ""
                    violations.append(
                        Violation(
                            severity=mode,
                            message=(
                                f"deprecated since {dep.since}, "
                                f"must be removed by {dep.remove_in} "
                                f"(planning {planned.current} → {planned.next})"
                                f"{suffix}"
                            ),
                            file=dep.file,
                            line=dep.line,
                            component=planned.component,
                            plugin=self.name,
                        )
                    )
        return violations

    def enrich_changelog(
        self, ctx: PluginContext, component: str
    ) -> list[ChangelogEntry]:
        """Contribute up to two sections per component:

        * ``Deprecated`` — markers newly added in this release window
          (``since`` falls between the previous version and the next).
        * ``Removed`` — markers whose ``remove_in`` ≤ next version
          (i.e. should be gone by the time this release ships).
        """
        if not self._enabled(ctx):
            return []
        planned: PlannedBump | None = ctx.plan.bumps.get(component)
        if planned is None:
            return []
        current = Version(str(planned.current))
        next_v = Version(planned.next)
        deps = self._scan_component(ctx, component)
        deprecated_lines: list[str] = []
        removed_lines: list[str] = []
        for dep in deps:
            label = (
                f"`{dep.file}:{dep.line}` (since {dep.since}, "
                f"remove in {dep.remove_in})"
            )
            if dep.message:
                label += f" — {dep.message}"
            if current < dep.since <= next_v:
                deprecated_lines.append(label)
            if dep.remove_in <= next_v:
                removed_lines.append(label)
        entries: list[ChangelogEntry] = []
        if deprecated_lines:
            entries.append(
                ChangelogEntry(
                    section="Deprecated",
                    component=component,
                    lines=tuple(deprecated_lines),
                )
            )
        if removed_lines:
            entries.append(
                ChangelogEntry(
                    section="Removed",
                    component=component,
                    lines=tuple(removed_lines),
                )
            )
        return entries

    def status_lines(self, ctx: PluginContext) -> list[str]:
        """Pre-flight summary surfaced by ``multicz status`` and
        ``multicz plan``: how many deprecations cross which thresholds
        for the planned next versions."""
        if not self._enabled(ctx):
            return []
        lines: list[str] = []
        for planned in ctx.plan:
            next_v = Version(planned.next)
            current = Version(str(planned.current))
            deps = self._scan_component(ctx, planned.component)
            if not deps:
                continue
            new_in_window = sum(1 for d in deps if current < d.since <= next_v)
            due = sum(1 for d in deps if d.remove_in <= next_v)
            upcoming = sum(1 for d in deps if next_v < d.remove_in)
            bits: list[str] = []
            if new_in_window:
                bits.append(f"{new_in_window} added")
            if due:
                bits.append(f"[bold red]{due} due for removal[/]")
            if upcoming:
                bits.append(f"{upcoming} upcoming")
            if bits:
                lines.append(
                    f"deprecation[{planned.component} {planned.current} → {planned.next}]: "
                    + ", ".join(bits)
                )
        return lines
