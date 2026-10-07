# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Plugin runner / hook-invocation tests."""

from __future__ import annotations

import warnings
from pathlib import Path
from types import SimpleNamespace

from multicz.plugins import (
    BasePlugin,
    ChangelogEntry,
    OwnershipContext,
    PluginContext,
    PluginRegistry,
    Severity,
    Violation,
    has_errors,
    run_affects,
    run_enrich_changelog,
    run_post_plan,
    run_status_lines,
    run_validate,
)

# Light-weight stand-in for the real multicz.config.Config —
# the runner only reads ``.plugins`` from it.
_FAKE_CONFIG = SimpleNamespace(plugins={"speaker": {"vol": 11}})
_FAKE_REPO = Path("/tmp/repo")
_FAKE_PLAN = object()


def _config_with(*names: str, **overrides) -> SimpleNamespace:
    """Build a fake config that opts every named plugin in.

    The runner's ``is_active`` gate requires each plugin's name to be a
    key in ``config.plugins``. Tests that want their plugin to actually
    run must therefore declare it — exactly mirroring the real opt-in
    model in multicz.toml. Per-plugin overrides can be passed as keyword
    args (e.g. ``_config_with("a", a={"enabled": False})``)."""
    return SimpleNamespace(plugins={n: overrides.get(n, {}) for n in names})


# ---------------------------------------------------------------------------
# Plugin config slicing
# ---------------------------------------------------------------------------


def test_plugin_receives_its_own_config_section():
    """A plugin named ``speaker`` reads ``[plugins.speaker]`` from
    multicz.toml — the runner injects only that slice into its
    :class:`PluginContext`."""
    captured: list[PluginContext] = []

    class Speaker(BasePlugin):
        name = "speaker"

        def post_plan(self, ctx):
            captured.append(ctx)
            return []

    run_post_plan(_FAKE_CONFIG, _FAKE_REPO, _FAKE_PLAN, registry=PluginRegistry([Speaker()]))
    assert captured[0].plugin_config == {"vol": 11}


def test_plugin_with_no_config_section_is_skipped():
    """The runner's gate requires explicit opt-in: a plugin whose name
    isn't listed under ``[plugins]`` is treated as inactive and never
    invoked, even if it's been discovered via an entry point."""
    captured: list[PluginContext] = []

    class Anonymous(BasePlugin):
        name = "anon"

        def post_plan(self, ctx):
            captured.append(ctx)
            return []

    run_post_plan(_FAKE_CONFIG, _FAKE_REPO, _FAKE_PLAN, registry=PluginRegistry([Anonymous()]))
    assert captured == []


def test_plugin_with_empty_section_runs_with_defaults():
    """An empty ``[plugins.<name>]`` section is the minimal opt-in form
    — the plugin must be invoked, with an empty ``plugin_config``."""
    captured: list[PluginContext] = []

    class Anonymous(BasePlugin):
        name = "anon"

        def post_plan(self, ctx):
            captured.append(ctx)
            return []

    run_post_plan(
        _config_with("anon"),
        _FAKE_REPO,
        _FAKE_PLAN,
        registry=PluginRegistry([Anonymous()]),
    )
    assert len(captured) == 1
    assert captured[0].plugin_config == {}


def test_plugin_disabled_via_enabled_false_is_skipped():
    """``enabled = false`` under a declared section opts the plugin out
    — the runner must skip it just like a missing section would."""
    captured: list[PluginContext] = []

    class Anonymous(BasePlugin):
        name = "anon"

        def post_plan(self, ctx):
            captured.append(ctx)
            return []

    cfg = SimpleNamespace(plugins={"anon": {"enabled": False, "vol": 11}})
    run_post_plan(cfg, _FAKE_REPO, _FAKE_PLAN, registry=PluginRegistry([Anonymous()]))
    assert captured == []


# ---------------------------------------------------------------------------
# run_post_plan — aggregation across plugins
# ---------------------------------------------------------------------------


def test_post_plan_aggregates_violations_across_plugins():
    class A(BasePlugin):
        name = "a"

        def post_plan(self, ctx):
            return [Violation(Severity.error, "boom", plugin=self.name)]

    class B(BasePlugin):
        name = "b"

        def post_plan(self, ctx):
            return [
                Violation(Severity.warning, "tut", plugin=self.name),
                Violation(Severity.info, "fyi", plugin=self.name),
            ]

    out = run_post_plan(
        _config_with("a", "b"),
        _FAKE_REPO,
        _FAKE_PLAN,
        registry=PluginRegistry([A(), B()]),
    )
    assert [v.plugin for v in out] == ["a", "b", "b"]
    assert [v.severity for v in out] == [Severity.error, Severity.warning, Severity.info]


def test_post_plan_with_no_plugins_returns_empty():
    out = run_post_plan(_FAKE_CONFIG, _FAKE_REPO, _FAKE_PLAN, registry=PluginRegistry([]))
    assert out == []


def test_has_errors_helper():
    assert has_errors([Violation(Severity.error, "x", plugin="p")]) is True
    assert has_errors([Violation(Severity.warning, "x", plugin="p")]) is False
    assert has_errors([Violation(Severity.info, "x", plugin="p")]) is False
    assert has_errors([]) is False
    assert (
        has_errors(
            [
                Violation(Severity.warning, "x", plugin="p"),
                Violation(Severity.error, "y", plugin="p"),
            ]
        )
        is True
    )


# ---------------------------------------------------------------------------
# Crashing plugin — warns + continues
# ---------------------------------------------------------------------------


def test_crashing_plugin_emits_warning_and_continues():
    """A plugin that raises in ``post_plan`` must not blow up the run —
    the runner emits a RuntimeWarning and other plugins still execute."""

    class Crashes(BasePlugin):
        name = "boom"

        def post_plan(self, ctx):
            raise RuntimeError("kaboom")

    class Ok(BasePlugin):
        name = "ok"

        def post_plan(self, ctx):
            return [Violation(Severity.info, "still here", plugin=self.name)]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = run_post_plan(
            _config_with("boom", "ok"),
            _FAKE_REPO,
            _FAKE_PLAN,
            registry=PluginRegistry([Crashes(), Ok()]),
        )
    assert [v.plugin for v in out] == ["ok"]
    assert any("raised in post_plan" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# run_enrich_changelog — per-component invocation
# ---------------------------------------------------------------------------


def test_enrich_changelog_aggregates_per_component():
    class P(BasePlugin):
        name = "p"

        def enrich_changelog(self, ctx, component):
            return [ChangelogEntry(section="Deprecated", component=component, lines=("foo",))]

    out = run_enrich_changelog(
        _config_with("p"),
        _FAKE_REPO,
        _FAKE_PLAN,
        "api",
        registry=PluginRegistry([P()]),
    )
    assert len(out) == 1
    assert out[0].component == "api"
    assert out[0].section == "Deprecated"
    assert out[0].lines == ("foo",)


# ---------------------------------------------------------------------------
# run_status_lines
# ---------------------------------------------------------------------------


def test_status_lines_concatenates_all_plugins():
    class A(BasePlugin):
        name = "a"

        def status_lines(self, ctx):
            return ["alpha"]

    class B(BasePlugin):
        name = "b"

        def status_lines(self, ctx):
            return ["bravo", "charlie"]

    out = run_status_lines(
        _config_with("a", "b"),
        _FAKE_REPO,
        _FAKE_PLAN,
        registry=PluginRegistry([A(), B()]),
    )
    assert out == ["alpha", "bravo", "charlie"]


def test_config_without_plugins_attribute_is_handled():
    """Old configs (or test stubs) that don't carry ``.plugins`` shouldn't
    crash the runner — they fall back to an empty plugins map, which
    means **no plugin is opted in**, so the runner skips everything."""
    captured: list[PluginContext] = []

    class P(BasePlugin):
        name = "anywhere"

        def post_plan(self, ctx):
            captured.append(ctx)
            return []

    bare_config = SimpleNamespace()  # no .plugins attribute
    run_post_plan(bare_config, _FAKE_REPO, _FAKE_PLAN, registry=PluginRegistry([P()]))
    assert captured == []


# ---------------------------------------------------------------------------
# run_affects
# ---------------------------------------------------------------------------


def test_affects_receives_component_and_paths():
    captured: list[tuple[OwnershipContext, str, list[str]]] = []

    class P(BasePlugin):
        name = "p"

        def affects(self, ctx, component, paths):
            captured.append((ctx, component, paths))
            return False

    run_affects(
        _config_with("p"),
        _FAKE_REPO,
        "api",
        ["internal/auth/token.go"],
        registry=PluginRegistry([P()]),
    )
    assert len(captured) == 1
    ctx, component, paths = captured[0]
    assert isinstance(ctx, OwnershipContext)
    assert ctx.repo == _FAKE_REPO
    assert component == "api"
    assert paths == ["internal/auth/token.go"]


def test_affects_true_short_circuits_remaining_plugins():
    """The first plugin to claim the component wins - a later one is
    never even asked, since the caller only needs a yes/no answer."""
    called: list[str] = []

    class Yes(BasePlugin):
        name = "yes"

        def affects(self, ctx, component, paths):
            called.append(self.name)
            return True

    class Never(BasePlugin):
        name = "never"

        def affects(self, ctx, component, paths):
            called.append(self.name)
            return True

    out = run_affects(
        _config_with("yes", "never"),
        _FAKE_REPO,
        "api",
        ["x"],
        registry=PluginRegistry([Yes(), Never()]),
    )
    assert out is True
    assert called == ["yes"]


def test_affects_false_tries_every_plugin():
    called: list[str] = []

    class A(BasePlugin):
        name = "a"

        def affects(self, ctx, component, paths):
            called.append(self.name)
            return False

    class B(BasePlugin):
        name = "b"

        def affects(self, ctx, component, paths):
            called.append(self.name)
            return False

    out = run_affects(
        _config_with("a", "b"),
        _FAKE_REPO,
        "api",
        ["x"],
        registry=PluginRegistry([A(), B()]),
    )
    assert out is False
    assert called == ["a", "b"]


def test_affects_default_base_plugin_returns_false():
    """A plugin that doesn't override ``affects`` has no opinion."""

    class Quiet(BasePlugin):
        name = "quiet"

    out = run_affects(
        _config_with("quiet"),
        _FAKE_REPO,
        "api",
        ["x"],
        registry=PluginRegistry([Quiet()]),
    )
    assert out is False


def test_affects_inactive_plugin_is_skipped():
    class Yes(BasePlugin):
        name = "yes"

        def affects(self, ctx, component, paths):
            return True

    out = run_affects(
        _FAKE_CONFIG,  # only "speaker" is opted in
        _FAKE_REPO,
        "api",
        ["x"],
        registry=PluginRegistry([Yes()]),
    )
    assert out is False


def test_affects_with_no_plugins_returns_false():
    out = run_affects(_FAKE_CONFIG, _FAKE_REPO, "api", ["x"], registry=PluginRegistry([]))
    assert out is False


def test_affects_crashing_plugin_treated_as_false():
    """A plugin that raises in ``affects`` must not abort ownership
    resolution - the runner warns and treats it as ``False``, then
    still asks the next plugin."""

    class Crashes(BasePlugin):
        name = "boom"

        def affects(self, ctx, component, paths):
            raise RuntimeError("kaboom")

    class Yes(BasePlugin):
        name = "yes"

        def affects(self, ctx, component, paths):
            return True

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = run_affects(
            _config_with("boom", "yes"),
            _FAKE_REPO,
            "api",
            ["x"],
            registry=PluginRegistry([Crashes(), Yes()]),
        )
    assert out is True
    assert any("raised in affects" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# run_validate
# ---------------------------------------------------------------------------


def test_validate_receives_an_ownership_context_with_its_config_slice():
    captured: list[OwnershipContext] = []

    class Checker(BasePlugin):
        name = "checker"

        def validate(self, ctx):
            captured.append(ctx)
            return []

    config = _config_with("checker", checker={"strict": True})
    run_validate(config, _FAKE_REPO, registry=PluginRegistry([Checker()]))
    assert isinstance(captured[0], OwnershipContext)
    assert captured[0].plugin_config == {"strict": True}
    assert captured[0].repo == _FAKE_REPO


def test_validate_violations_are_tagged_with_their_plugin():
    class Checker(BasePlugin):
        name = "checker"

        def validate(self, ctx):
            return [
                Violation(Severity.error, "go list failed", component="api"),
                Violation(Severity.warning, "named", plugin="other"),
            ]

    out = run_validate(_config_with("checker"), _FAKE_REPO, registry=PluginRegistry([Checker()]))
    assert [(v.severity, v.plugin, v.component) for v in out] == [
        (Severity.error, "checker", "api"),
        (Severity.warning, "other", None),
    ]


def test_validate_default_inactive_and_crashing_plugins_report_nothing():
    class Quiet(BasePlugin):
        name = "quiet"

    class Loud(BasePlugin):
        name = "loud"

        def validate(self, ctx):
            return [Violation(Severity.error, "never seen")]

    class Crash(BasePlugin):
        name = "crash"

        def validate(self, ctx):
            raise RuntimeError("boom")

    registry = PluginRegistry([Quiet(), Loud(), Crash()])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = run_validate(_config_with("quiet", "crash"), _FAKE_REPO, registry=registry)
    assert out == []
    assert any("raised in validate()" in str(w.message) for w in caught)
