# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

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
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .protocol import ChangelogEntry, OwnershipContext, PluginContext, Severity, Violation
from .registry import DEFAULT_REGISTRY, PluginRegistry

if TYPE_CHECKING:
    from ..planner import Plan


def _plugin_config(config: Any, plugin_name: str) -> dict[str, Any]:
    """The ``[plugins.<plugin_name>]`` slice of ``config``, or ``{}``."""
    plugins_table: dict[str, dict[str, Any]] = getattr(config, "plugins", {}) or {}
    return plugins_table.get(plugin_name, {})


def _make_context(config: Any, repo: Path, plan: Plan, plugin_name: str) -> PluginContext:
    """Build a :class:`PluginContext` slicing the plugin's own config
    section out of ``config.plugins[plugin_name]`` (default empty dict)."""
    return PluginContext(
        config=config,
        repo=repo,
        plan=plan,
        plugin_config=_plugin_config(config, plugin_name),
    )


def _make_ownership_context(config: Any, repo: Path, plugin_name: str) -> OwnershipContext:
    """Build an :class:`OwnershipContext` for :meth:`Plugin.affects` -
    same config slicing as :func:`_make_context`, no ``plan`` to carry."""
    return OwnershipContext(
        config=config,
        repo=repo,
        plugin_config=_plugin_config(config, plugin_name),
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


def _safe_call(plugin, method_name, *args, default=None, **kwargs):
    """Invoke a plugin hook, swallowing exceptions as warnings.

    A plugin that crashes during one invocation MUST NOT take down the
    rest of the run — multicz emits a ``RuntimeWarning`` and treats the
    hook as if it returned ``default`` (an empty list for every
    list-returning hook, the default here; ``affects`` passes ``False``)."""
    try:
        return getattr(plugin, method_name)(*args, **kwargs)
    except Exception as exc:
        warnings.warn(
            f"multicz: plugin {plugin.name!r} raised in {method_name}(): {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return [] if default is None else default


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


def run_affects(
    config: Any,
    repo: Path,
    component: str,
    paths: list[str],
    *,
    registry: PluginRegistry | None = None,
) -> bool:
    """``True`` if any active plugin's :meth:`Plugin.affects` claims
    ``component`` for any of ``paths``.

    Short-circuits on the first plugin that claims it - callers only
    ever need a yes/no answer, and ``affects`` is documented as
    something a plugin may call out to an external, possibly
    expensive, process to compute."""
    reg = registry or DEFAULT_REGISTRY
    for plugin in reg:
        if not is_active(config, plugin.name):
            continue
        ctx = _make_ownership_context(config, repo, plugin.name)
        if _safe_call(plugin, "affects", ctx, component, paths, default=False):
            return True
    return False


def run_validate(
    config: Any,
    repo: Path,
    *,
    registry: PluginRegistry | None = None,
) -> list[Violation]:
    """Invoke :meth:`Plugin.validate` on every active plugin.

    Each violation carries the name of the plugin that reported it, so
    ``multicz validate`` can say where a finding comes from."""
    reg = registry or DEFAULT_REGISTRY
    violations: list[Violation] = []
    for plugin in reg:
        if not is_active(config, plugin.name):
            continue
        ctx = _make_ownership_context(config, repo, plugin.name)
        for violation in _safe_call(plugin, "validate", ctx):
            violations.append(
                violation if violation.plugin else replace(violation, plugin=plugin.name)
            )
    return violations


def has_errors(violations: list[Violation]) -> bool:
    """``True`` iff any violation is ``Severity.error`` (i.e. the bump
    should abort)."""
    return any(v.severity == Severity.error for v in violations)
