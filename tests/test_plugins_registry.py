# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Plugin protocol + registry tests."""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from multicz.plugins import (
    BasePlugin,
    ChangelogEntry,
    Plugin,
    PluginContext,
    PluginRegistry,
    Severity,
    Violation,
)

# ---------------------------------------------------------------------------
# Protocol — BasePlugin defaults + duck typing
# ---------------------------------------------------------------------------


def test_base_plugin_satisfies_protocol():
    """Subclassing ``BasePlugin`` is enough to satisfy the Plugin protocol
    — no need to manually implement every hook."""

    class Noop(BasePlugin):
        name = "noop"

    assert isinstance(Noop(), Plugin)


def test_base_plugin_all_hooks_default_to_empty_list():
    class Noop(BasePlugin):
        name = "noop"

    p = Noop()
    ctx = PluginContext(config=None, repo=Path("."), plan=None, plugin_config={})
    assert p.post_plan(ctx) == []
    assert p.enrich_changelog(ctx, "api") == []
    assert p.status_lines(ctx) == []


def test_plugin_can_override_just_one_hook():
    """Plugins implement only the hooks they care about; the rest
    inherit the no-op default."""

    class OnlyPostPlan(BasePlugin):
        name = "only-post-plan"

        def post_plan(self, ctx):
            return [Violation(Severity.warning, "hi", plugin=self.name)]

    ctx = PluginContext(config=None, repo=Path("."), plan=None, plugin_config={})
    p = OnlyPostPlan()
    assert len(p.post_plan(ctx)) == 1
    assert p.enrich_changelog(ctx, "api") == []  # inherited no-op


# ---------------------------------------------------------------------------
# Violation / ChangelogEntry dataclasses
# ---------------------------------------------------------------------------


def test_violation_is_frozen():
    from dataclasses import FrozenInstanceError

    v = Violation(Severity.error, "boom", plugin="x")
    with pytest.raises(FrozenInstanceError):
        v.severity = Severity.info  # type: ignore[misc]


def test_violation_optional_location_fields():
    v = Violation(Severity.warning, "deprecated", plugin="dep")
    assert v.file is None
    assert v.line is None
    assert v.component is None


def test_changelog_entry_lines_default_empty():
    e = ChangelogEntry(section="Deprecated", component="api")
    assert e.lines == ()


# ---------------------------------------------------------------------------
# Registry — explicit seeding
# ---------------------------------------------------------------------------


def test_registry_accepts_explicit_plugins():
    class A(BasePlugin):
        name = "a"

    class B(BasePlugin):
        name = "b"

    reg = PluginRegistry([A(), B()])
    assert len(reg) == 2
    assert {p.name for p in reg} == {"a", "b"}


def test_registry_get_by_name():
    class P(BasePlugin):
        name = "lookup"

    reg = PluginRegistry([P()])
    assert reg.get("lookup") is not None
    assert reg.get("nope") is None


def test_explicit_registry_skips_entry_point_discovery():
    """Seeding with a list should never trigger entry-point lookup —
    so tests are isolated from whatever's installed on the user's
    machine."""
    sentinel = BasePlugin()
    sentinel.name = "sentinel"
    reg = PluginRegistry([sentinel])
    with patch("multicz.plugins.registry.importlib.metadata.entry_points") as mock_ep:
        assert reg.all() == [sentinel]
        mock_ep.assert_not_called()


# ---------------------------------------------------------------------------
# Registry — entry-point discovery + error handling
# ---------------------------------------------------------------------------


def test_registry_discovers_entry_points():
    """An empty registry pulls from the ``multicz.plugins`` entry-point
    group on first access."""

    class FakePlugin(BasePlugin):
        name = "fake"

    class FakeEntryPoint:
        name = "fake"

        def load(self):
            return FakePlugin

    with patch(
        "multicz.plugins.registry.importlib.metadata.entry_points",
        return_value=[FakeEntryPoint()],
    ):
        reg = PluginRegistry()
        plugins = reg.all()
        assert len(plugins) == 1
        assert plugins[0].name == "fake"


def test_registry_skips_plugin_that_fails_to_load():
    """A plugin whose ``ep.load()`` raises must not crash the whole
    registry — it's logged as a warning and skipped."""

    class GoodPlugin(BasePlugin):
        name = "good"

    class BadEntryPoint:
        name = "bad"

        def load(self):
            raise ImportError("module missing")

    class GoodEntryPoint:
        name = "good"

        def load(self):
            return GoodPlugin

    with patch(
        "multicz.plugins.registry.importlib.metadata.entry_points",
        return_value=[BadEntryPoint(), GoodEntryPoint()],
    ):
        reg = PluginRegistry()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            plugins = reg.all()
        assert len(plugins) == 1
        assert plugins[0].name == "good"
        assert any("failed to load plugin" in str(w.message) for w in caught)


def test_registry_skips_non_protocol_plugin():
    """If an entry point loads something that doesn't satisfy the
    Plugin protocol, it's skipped with a warning rather than corrupting
    downstream hook iteration."""

    class NotAPlugin:
        """No `name` attr, no hooks — definitely not a Plugin."""

    class BadEntryPoint:
        name = "broken"

        def load(self):
            return NotAPlugin

    with patch(
        "multicz.plugins.registry.importlib.metadata.entry_points",
        return_value=[BadEntryPoint()],
    ):
        reg = PluginRegistry()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            plugins = reg.all()
        assert plugins == []
        assert any("does not satisfy the Plugin protocol" in str(w.message) for w in caught)


def test_registry_caches_discovery():
    """Subsequent ``.all()`` calls reuse the discovered list — entry
    points are NOT re-scanned each time."""

    class P(BasePlugin):
        name = "cached"

    class EP:
        name = "cached"

        def load(self):
            return P

    with patch(
        "multicz.plugins.registry.importlib.metadata.entry_points",
        return_value=[EP()],
    ) as mock_ep:
        reg = PluginRegistry()
        reg.all()
        reg.all()
        reg.all()
        assert mock_ep.call_count == 1
