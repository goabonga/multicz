# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Plugin protocol — the contract every multicz plugin implements.

Hooks are wired into specific stages of the bump pipeline:

* :meth:`Plugin.post_plan` runs after :func:`multicz.planner.build_plan`
  has computed what each component would bump to, but BEFORE any write.
  Return :class:`Violation` objects to surface errors / warnings.
  ``Severity.error`` aborts the bump entirely.

* :meth:`Plugin.enrich_changelog` runs while the markdown changelog or
  GitHub release notes are being rendered. Return :class:`ChangelogEntry`
  objects to inject extra sections (e.g. ``Deprecated``, ``Removed``).

* :meth:`Plugin.status_lines` is invoked by ``multicz status`` and
  ``multicz plan`` to add actionable lines (e.g. "3 deprecations marked
  for removal in v3.0 — your plan bumps to v3.0, please drop them").

* :meth:`Plugin.affects` runs BEFORE a plan exists, while ``multicz
  changed`` and the planner's own direct-change pass are each deciding
  which components a changed path touches. Return ``True`` to claim
  ``component`` for ``paths`` beyond whatever ``multicz.toml``'s own
  ``paths`` glob patterns already matched - the escape hatch for
  ownership a glob cannot express, such as a language's own real
  import graph. The two callers OR this in with their path-based
  match; a plugin with no opinion returns ``False`` and changes
  nothing. Call frequency varies by caller - see below.

* :meth:`Plugin.validate` runs during ``multicz validate``, with no plan
  either. Return :class:`Violation` objects for whatever would make the
  plugin's other hooks answer wrongly (a dependency query that fails,
  a config section it cannot use); they are reported as validation
  findings, so ``Severity.error`` fails the command and
  ``Severity.warning`` fails it under ``--strict``.

Plugins are read-only with respect to the plan and config; they MUST
NOT mutate either. Side effects (logging, network) are allowed but
discouraged — keep hooks fast (<500ms). Call frequency for ``affects``
varies by caller: ``multicz changed`` calls it once per component with
every changed path in its comparison window already batched together;
the planner's direct-change pass calls it once per (component, commit)
pair, but only when that commit's files did not already match via
``paths`` - most commits never reach it. Either way, a plugin backed
by an expensive external call (a compiler's dependency graph, say)
should memoize per component internally rather than recomputing it on
every invocation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..planner import Plan


class Severity(StrEnum):
    """Plugin-reported severity. ``error`` aborts; ``warning`` informs."""

    error = "error"
    warning = "warning"
    info = "info"


@dataclass(frozen=True)
class Violation:
    """A single finding surfaced by a plugin's :meth:`Plugin.post_plan`.

    File / line are optional — use them when the finding has a precise
    location in the source tree so editor-style "click to jump" output
    can render it.
    """

    severity: Severity
    message: str
    file: Path | None = None
    line: int | None = None
    component: str | None = None
    plugin: str = ""


@dataclass(frozen=True)
class ChangelogEntry:
    """A custom changelog / release-notes section a plugin contributes.

    ``section`` is the H3 heading (e.g. ``"Deprecated"`` / ``"Removed"``).
    ``lines`` are the bullet body — already formatted markdown lines.
    """

    section: str
    component: str
    lines: tuple[str, ...] = ()


@dataclass
class PluginContext:
    """Read-only context handed to every hook.

    ``plugin_config`` is the relevant slice of the user's ``multicz.toml``
    — typically the ``[plugins.<name>]`` table — already coerced to a
    plain dict. Plugins read defaults from it; the core never injects
    them.
    """

    config: Any  # multicz.config.Config — Any to avoid circular import
    repo: Path
    plan: Plan
    plugin_config: dict[str, Any]


@dataclass
class OwnershipContext:
    """Read-only context handed to :meth:`Plugin.affects` and
    :meth:`Plugin.validate`.

    Lighter than :class:`PluginContext`: ``affects`` runs while multicz
    is still deciding which components a change touches, and
    ``validate`` checks the configuration, both before any
    :class:`Plan` exists to put in one.
    """

    config: Any  # multicz.config.Config — Any to avoid circular import
    repo: Path
    plugin_config: dict[str, Any]


@runtime_checkable
class Plugin(Protocol):
    """Public protocol every multicz plugin satisfies.

    All hook methods are OPTIONAL — :class:`BasePlugin` provides no-op
    defaults so concrete plugins only implement the hooks they care
    about. The Protocol is :func:`typing.runtime_checkable` so
    ``isinstance(x, Plugin)`` is a valid duck-type check at runtime.
    """

    name: str
    """Unique identifier. Drives the ``[plugins.<name>]`` config section
    and namespaces violations / changelog entries in CLI output."""

    def post_plan(self, ctx: PluginContext) -> list[Violation]: ...

    def enrich_changelog(
        self, ctx: PluginContext, component: str
    ) -> list[ChangelogEntry]: ...

    def status_lines(self, ctx: PluginContext) -> list[str]: ...

    def affects(
        self, ctx: OwnershipContext, component: str, paths: list[str]
    ) -> bool: ...

    def validate(self, ctx: OwnershipContext) -> list[Violation]: ...


class BasePlugin:
    """Convenience base — every hook is a no-op by default.

    Concrete plugins inherit and override only what they need::

        class MyPlugin(BasePlugin):
            name = "my-plugin"

            def post_plan(self, ctx):
                return [Violation(Severity.warning, "hello", plugin=self.name)]
    """

    name: str = "<unset>"

    def post_plan(self, ctx: PluginContext) -> list[Violation]:
        return []

    def enrich_changelog(
        self, ctx: PluginContext, component: str
    ) -> list[ChangelogEntry]:
        return []

    def status_lines(self, ctx: PluginContext) -> list[str]:
        return []

    def affects(
        self, ctx: OwnershipContext, component: str, paths: list[str]
    ) -> bool:
        return False

    def validate(self, ctx: OwnershipContext) -> list[Violation]:
        return []
