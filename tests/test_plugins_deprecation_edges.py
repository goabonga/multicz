# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Deprecation plugin edge cases: config fallbacks and disabled hooks."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from multicz.plugins import PluginContext, Severity
from multicz.plugins.builtin.deprecation import DeprecationPlugin


def _ctx(
    repo: Path, bumps: dict, plugin_config: dict | None = None, components: dict | None = None
):
    config = SimpleNamespace(components=components or {})
    plan = type(
        "FakePlan",
        (),
        {"bumps": bumps, "__iter__": lambda self: iter(self.bumps.values())},
    )()
    return PluginContext(config=config, repo=repo, plan=plan, plugin_config=plugin_config or {})


def _planned(component: str, current: str, next_version: str):
    return SimpleNamespace(component=component, current=current, next=next_version)


def test_invalid_mode_falls_back_to_error(tmp_path: Path):
    (tmp_path / "api.py").write_text('@deprecated(since="1.0.0", remove_in="2.0.0")\n')
    ctx = _ctx(
        tmp_path,
        {"api": _planned("api", "1.5.0", "2.0.0")},
        {"scan": ["*.py"], "mode": "bogus"},
    )
    [violation] = DeprecationPlugin().post_plan(ctx)
    assert violation.severity == Severity.error


def test_per_component_scan_overrides_global(tmp_path: Path):
    (tmp_path / "api.py").write_text('@deprecated(since="1.0.0", remove_in="2.0.0")\n')
    (tmp_path / "other.py").write_text('@deprecated(since="1.0.0", remove_in="2.0.0")\n')
    ctx = _ctx(
        tmp_path,
        {"api": _planned("api", "1.5.0", "2.0.0")},
        {"scan": ["other.py"], "scan_per_component": {"api": ["api.py"]}},
    )
    [violation] = DeprecationPlugin().post_plan(ctx)
    assert violation.file.name == "api.py"


def test_unknown_component_without_scan_yields_no_globs(tmp_path: Path):
    ctx = _ctx(tmp_path, {})
    assert DeprecationPlugin()._scan_globs_for(ctx, "ghost") == []


def test_enrich_changelog_disabled_returns_nothing(tmp_path: Path):
    ctx = _ctx(
        tmp_path,
        {"api": _planned("api", "1.0.0", "2.0.0")},
        {"enabled": False},
    )
    assert DeprecationPlugin().enrich_changelog(ctx, "api") == []


def test_enrich_changelog_includes_marker_message(tmp_path: Path):
    (tmp_path / "x.py").write_text("x = 1  # DEPRECATED since=1.5.0 remove_in=2.0.0 - use y\n")
    ctx = _ctx(
        tmp_path,
        {"api": _planned("api", "1.0.0", "2.0.0")},
        {"scan": ["*.py"]},
    )
    entries = DeprecationPlugin().enrich_changelog(ctx, "api")
    assert [e.section for e in entries] == ["Deprecated", "Removed"]
    assert all("use y" in line for e in entries for line in e.lines)


def test_status_lines_disabled_returns_nothing(tmp_path: Path):
    ctx = _ctx(
        tmp_path,
        {"api": _planned("api", "1.0.0", "2.0.0")},
        {"enabled": False},
    )
    assert DeprecationPlugin().status_lines(ctx) == []
