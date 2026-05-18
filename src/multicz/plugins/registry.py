# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Plugin discovery via ``importlib.metadata`` entry points.

Any installed package that declares::

    [project.entry-points."multicz.plugins"]
    deprecation = "my_pkg.plugin:MyPlugin"

is auto-discovered. multicz itself registers its built-in plugins the
same way (see this project's ``pyproject.toml``).

Discovery is lazy + cached on first access so importing the registry
module has zero cost. Failures during plugin instantiation are
swallowed with a warning — one broken plugin must not take down the
whole CLI.
"""

from __future__ import annotations

import importlib.metadata
import warnings
from collections.abc import Iterator

from .protocol import Plugin

ENTRY_POINT_GROUP = "multicz.plugins"


class PluginRegistry:
    """Lazy discovery + caching of installed plugins.

    Pass ``plugins=`` to the constructor to seed the registry with an
    explicit list (useful in tests where entry-point discovery would
    leak in third-party plugins). Pass nothing to fall back to entry
    points on first :meth:`all` call.
    """

    def __init__(self, plugins: list[Plugin] | None = None) -> None:
        self._plugins: list[Plugin] | None = plugins

    def all(self) -> list[Plugin]:
        """Return the full list of registered plugins, discovering on
        first call if no explicit list was provided."""
        if self._plugins is None:
            self._plugins = self._discover()
        return self._plugins

    def get(self, name: str) -> Plugin | None:
        """Find a plugin by ``name`` (the value of ``Plugin.name``)."""
        for plugin in self.all():
            if plugin.name == name:
                return plugin
        return None

    def _discover(self) -> list[Plugin]:
        discovered: list[Plugin] = []
        for ep in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
            try:
                loaded = ep.load()
                instance = loaded() if callable(loaded) else loaded
            except Exception as exc:
                warnings.warn(
                    f"multicz: failed to load plugin {ep.name!r}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
            if not isinstance(instance, Plugin):
                warnings.warn(
                    f"multicz: plugin {ep.name!r} does not satisfy the Plugin "
                    "protocol — skipping",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
            discovered.append(instance)
        return discovered

    def __iter__(self) -> Iterator[Plugin]:
        return iter(self.all())

    def __len__(self) -> int:
        return len(self.all())


# Module-level singleton used by CLI commands. Tests can monkey-patch
# this or build their own ``PluginRegistry([...])`` for isolation.
DEFAULT_REGISTRY = PluginRegistry()
