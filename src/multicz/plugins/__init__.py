# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""multicz plugin system.

Plugins extend the bump / planning / changelog pipeline without touching
the core. They are discovered via the ``multicz.plugins`` entry-point
group (``importlib.metadata``), so any package on PYTHONPATH that
registers an entry point participates automatically.

Built-in plugins live under :mod:`multicz.plugins.builtin` and are
registered in multicz's own pyproject.toml.

See :mod:`multicz.plugins.protocol` for the hook contract.
"""

from .protocol import (
    BasePlugin,
    ChangelogEntry,
    Plugin,
    PluginContext,
    Severity,
    Violation,
)
from .registry import DEFAULT_REGISTRY, ENTRY_POINT_GROUP, PluginRegistry
from .runner import (
    has_errors,
    run_enrich_changelog,
    run_post_plan,
    run_status_lines,
)

__all__ = [
    "BasePlugin",
    "ChangelogEntry",
    "DEFAULT_REGISTRY",
    "ENTRY_POINT_GROUP",
    "Plugin",
    "PluginContext",
    "PluginRegistry",
    "Severity",
    "Violation",
    "has_errors",
    "run_enrich_changelog",
    "run_post_plan",
    "run_status_lines",
]
