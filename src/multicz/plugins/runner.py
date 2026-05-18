# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Hook invocation helpers used by CLI commands.

The runner sits between the CLI and the plugin protocol. It owns:

* Building the :class:`PluginContext` from ``(config, repo, plan)``.
* Iterating the registry and calling the requested hook on each plugin.
* Aggregating return values into a single flat list.

CLI commands stay thin — they call one of the ``run_*`` helpers,
inspect / print the aggregated result, and let the runner deal with
exceptions or plugin misbehaviour.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .protocol import ChangelogEntry, PluginContext, Severity, Violation
from .registry import DEFAULT_REGISTRY, PluginRegistry

if TYPE_CHECKING:
    from ..planner import Plan


def _make_context(config: Any, repo: Path, plan: Plan, plugin_name: str) -> PluginContext:
    """Build a :class:`PluginContext` slicing the plugin's own config
    section out of ``config.plugins[plugin_name]`` (default empty dict)."""
    plugins_table: dict[str, dict[str, Any]] = getattr(config, "plugins", {}) or {}
    return PluginContext(
        config=config,
        repo=repo,
        plan=plan,
        plugin_config=plugins_table.get(plugin_name, {}),
    )


def is_active(config: Any, plugin_name: str) -> bool:
    """``True`` when the plugin should be invoked by the run_* helpers.

    A plugin is active iff:
      1. ``[plugins.<name>]`` exists in multicz.toml (even empty) — this
         is the **explicit opt-in**. Discovery via entry points is not
         enough to make a plugin run; the project must declare it.
      2. AND ``enabled`` is not explicitly ``false`` under that section.

    Rationale: a freshly-installed plugin shouldn't silently gate the
    bump pipeline of every project that happens to have it on PYTHONPATH.
    Projects opt in by adding the section; an empty ``[plugins.deprecation]``
    means "yes, please run with all defaults".
    """
    plugins_table: dict[str, dict[str, Any]] = getattr(config, "plugins", {}) or {}
    if plugin_name not in plugins_table:
        return False
    section = plugins_table.get(plugin_name) or {}
    return bool(section.get("enabled", True))


def _safe_call(plugin, method_name, *args, **kwargs):
    """Invoke a plugin hook, swallowing exceptions as warnings.

    A plugin that crashes during one invocation MUST NOT take down the
    rest of the run — multicz emits a ``RuntimeWarning`` and treats the
    hook as if it returned an empty list."""
    try:
        return getattr(plugin, method_name)(*args, **kwargs)
    except Exception as exc:
        warnings.warn(
            f"multicz: plugin {plugin.name!r} raised in {method_name}(): {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return []


def run_post_plan(
    config: Any,
    repo: Path,
    plan: Plan,
    *,
    registry: PluginRegistry | None = None,
) -> list[Violation]:
    """Invoke :meth:`Plugin.post_plan` on every registered plugin.

    Returns the flat aggregated list of violations. Caller decides what
    to do with them (display, abort on errors, etc.)."""
    reg = registry or DEFAULT_REGISTRY
    violations: list[Violation] = []
    for plugin in reg:
        if not is_active(config, plugin.name):
            continue
        ctx = _make_context(config, repo, plan, plugin.name)
        results = _safe_call(plugin, "post_plan", ctx)
        violations.extend(results)
    return violations


def run_enrich_changelog(
    config: Any,
    repo: Path,
    plan: Plan,
    component: str,
    *,
    registry: PluginRegistry | None = None,
) -> list[ChangelogEntry]:
    """Invoke :meth:`Plugin.enrich_changelog` for ``component`` on every
    registered plugin. Returns the flat list of contributed sections."""
    reg = registry or DEFAULT_REGISTRY
    entries: list[ChangelogEntry] = []
    for plugin in reg:
        if not is_active(config, plugin.name):
            continue
        ctx = _make_context(config, repo, plan, plugin.name)
        results = _safe_call(plugin, "enrich_changelog", ctx, component)
        entries.extend(results)
    return entries


def run_status_lines(
    config: Any,
    repo: Path,
    plan: Plan,
    *,
    registry: PluginRegistry | None = None,
) -> list[str]:
    """Invoke :meth:`Plugin.status_lines` on every registered plugin.

    Returns the flat aggregated list of advice lines for the CLI to
    print alongside the bump table."""
    reg = registry or DEFAULT_REGISTRY
    lines: list[str] = []
    for plugin in reg:
        if not is_active(config, plugin.name):
            continue
        ctx = _make_context(config, repo, plan, plugin.name)
        results = _safe_call(plugin, "status_lines", ctx)
        lines.extend(results)
    return lines


def has_errors(violations: list[Violation]) -> bool:
    """``True`` iff any violation is ``Severity.error`` (i.e. the bump
    should abort)."""
    return any(v.severity == Severity.error for v in violations)
