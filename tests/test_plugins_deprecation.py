# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Built-in deprecation plugin — scanner + post_plan + enrich_changelog
+ status_lines."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from multicz.plugins import PluginContext, Severity
from multicz.plugins.builtin.deprecation import DeprecationPlugin
from multicz.plugins.builtin.deprecation.scanner import Deprecation, scan_paths


# ---------------------------------------------------------------------------
# Scanner — decorator + comment forms
# ---------------------------------------------------------------------------


def test_scanner_finds_decorator_marker(tmp_path: Path):
    src = tmp_path / "old.py"
    src.write_text(
        '@deprecated(since="1.2.0", remove_in="3.0.0")\n'
        'def legacy(): pass\n'
    )
    found = scan_paths(tmp_path, ["*.py"])
    assert len(found) == 1
    assert found[0].since.public == "1.2.0"
    assert found[0].remove_in.public == "3.0.0"
    assert found[0].line == 1


def test_scanner_finds_decorator_reversed_kwargs(tmp_path: Path):
    """``@deprecated(remove_in=..., since=...)`` must be accepted too."""
    src = tmp_path / "old.py"
    src.write_text('@deprecated(remove_in="3.0", since="1.2")\n')
    found = scan_paths(tmp_path, ["*.py"])
    assert len(found) == 1
    assert found[0].since.public == "1.2"
    assert found[0].remove_in.public == "3.0"


def test_scanner_finds_python_comment(tmp_path: Path):
    src = tmp_path / "x.py"
    src.write_text(
        "x = 1  # DEPRECATED since=1.0.0 remove_in=2.0.0 — use y instead\n"
    )
    found = scan_paths(tmp_path, ["*.py"])
    assert len(found) == 1
    assert found[0].message == "use y instead"


def test_scanner_finds_c_style_and_html_comments(tmp_path: Path):
    (tmp_path / "a.js").write_text("// DEPRECATED since=1.0 remove_in=2.0\n")
    (tmp_path / "b.html").write_text(
        "<!-- DEPRECATED since=1.0 remove_in=2.0 -->\n"
    )
    found = scan_paths(tmp_path, ["*.js", "*.html"])
    assert {str(d.file).split("/")[-1] for d in found} == {"a.js", "b.html"}


def test_scanner_skips_invalid_versions(tmp_path: Path):
    src = tmp_path / "bogus.py"
    src.write_text(
        "# DEPRECATED since=not-a-version remove_in=also-bogus\n"
        '@deprecated(since="ok", remove_in="oops")\n'
    )
    assert scan_paths(tmp_path, ["*.py"]) == []


def test_scanner_silently_skips_binary_files(tmp_path: Path):
    """A non-UTF-8 file in a scanned path should not crash the scan."""
    (tmp_path / "icon.png").write_bytes(b"\x89PNG\x00\x00\x00\xff invalid utf8")
    (tmp_path / "real.py").write_text(
        '@deprecated(since="1.0", remove_in="2.0")\n'
    )
    found = scan_paths(tmp_path, ["*.png", "*.py"])
    assert len(found) == 1
    assert found[0].file.name == "real.py"


def test_scanner_dedups_same_file_line(tmp_path: Path):
    """Same path matched by two globs must yield a single marker."""
    src = tmp_path / "x.py"
    src.write_text('@deprecated(since="1.0", remove_in="2.0")\n')
    found = scan_paths(tmp_path, ["*.py", "x.py"])
    assert len(found) == 1


def test_scanner_recursive_globs(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "deep").mkdir()
    (tmp_path / "pkg" / "deep" / "old.py").write_text(
        '@deprecated(since="1.0", remove_in="2.0")\n'
    )
    found = scan_paths(tmp_path, ["**/*.py"])
    assert len(found) == 1


# ---------------------------------------------------------------------------
# Plugin — post_plan policy enforcement
# ---------------------------------------------------------------------------


def _make_ctx(
    repo: Path,
    plan_bumps: dict,
    plugin_config: dict | None = None,
    components: dict | None = None,
):
    """Build a synthetic PluginContext for unit tests.

    Uses SimpleNamespace stubs for Config / Component / Plan so we
    don't pull the heavy Pydantic surface into every test.
    """
    components = components or {}
    config = SimpleNamespace(components=components)
    plan = SimpleNamespace(
        bumps=plan_bumps,
        __iter__=lambda self: iter(self.bumps.values()),
    )
    # Bind __iter__ properly on the instance.
    plan = type("FakePlan", (), {
        "bumps": plan_bumps,
        "__iter__": lambda self: iter(self.bumps.values()),
    })()
    return PluginContext(
        config=config,
        repo=repo,
        plan=plan,
        plugin_config=plugin_config or {},
    )


def _planned(component: str, current: str, next_version: str):
    """Stand-in PlannedBump — only ``component``, ``current``, ``next``
    are touched by the plugin."""
    return SimpleNamespace(component=component, current=current, next=next_version)


def test_post_plan_flags_marker_due_for_removal(tmp_path: Path):
    (tmp_path / "api.py").write_text(
        '@deprecated(since="1.0.0", remove_in="3.0.0")\n'
    )
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "2.0.0", "3.0.0")},
        plugin_config={"scan": ["*.py"]},
    )
    violations = DeprecationPlugin().post_plan(ctx)
    assert len(violations) == 1
    assert violations[0].severity == Severity.error
    assert "must be removed by 3.0.0" in violations[0].message
    assert violations[0].component == "api"


def test_post_plan_no_violation_when_remove_in_far_future(tmp_path: Path):
    (tmp_path / "api.py").write_text(
        '@deprecated(since="1.0.0", remove_in="5.0.0")\n'
    )
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "2.0.0", "2.1.0")},
        plugin_config={"scan": ["*.py"]},
    )
    assert DeprecationPlugin().post_plan(ctx) == []


def test_post_plan_warning_mode(tmp_path: Path):
    (tmp_path / "api.py").write_text(
        '@deprecated(since="1.0.0", remove_in="2.0.0")\n'
    )
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "1.5.0", "2.0.0")},
        plugin_config={"scan": ["*.py"], "mode": "warning"},
    )
    violations = DeprecationPlugin().post_plan(ctx)
    assert len(violations) == 1
    assert violations[0].severity == Severity.warning


def test_post_plan_disabled_returns_nothing(tmp_path: Path):
    (tmp_path / "api.py").write_text(
        '@deprecated(since="1.0.0", remove_in="2.0.0")\n'
    )
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "1.5.0", "2.0.0")},
        plugin_config={"scan": ["*.py"], "enabled": False},
    )
    assert DeprecationPlugin().post_plan(ctx) == []


def test_post_plan_falls_back_to_component_paths(tmp_path: Path):
    """No ``scan`` config → plugin falls back to the component's own
    ``paths`` — zero-config deployment."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text(
        '@deprecated(since="1.0.0", remove_in="2.0.0")\n'
    )
    fake_component = SimpleNamespace(paths=["src/**/*.py"])
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "1.5.0", "2.0.0")},
        plugin_config={},
        components={"api": fake_component},
    )
    violations = DeprecationPlugin().post_plan(ctx)
    assert len(violations) == 1


# ---------------------------------------------------------------------------
# Plugin — enrich_changelog
# ---------------------------------------------------------------------------


def test_enrich_changelog_emits_deprecated_section_for_new_markers(tmp_path: Path):
    """A marker whose ``since`` falls in the (current, next] window is
    a NEW deprecation for this release — surface it under ``Deprecated``."""
    (tmp_path / "api.py").write_text(
        '@deprecated(since="2.0.0", remove_in="4.0.0")\n'
    )
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "1.5.0", "2.0.0")},
        plugin_config={"scan": ["*.py"]},
    )
    entries = DeprecationPlugin().enrich_changelog(ctx, "api")
    sections = {e.section for e in entries}
    assert "Deprecated" in sections
    assert "Removed" not in sections  # remove_in=4.0 still in future


def test_enrich_changelog_emits_removed_section_for_due_markers(tmp_path: Path):
    (tmp_path / "api.py").write_text(
        '@deprecated(since="1.0.0", remove_in="3.0.0")\n'
    )
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "2.0.0", "3.0.0")},
        plugin_config={"scan": ["*.py"]},
    )
    entries = DeprecationPlugin().enrich_changelog(ctx, "api")
    sections = {e.section for e in entries}
    assert "Removed" in sections


def test_enrich_changelog_for_unknown_component_returns_empty(tmp_path: Path):
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "1.0.0", "2.0.0")},
        plugin_config={"scan": ["*.py"]},
    )
    assert DeprecationPlugin().enrich_changelog(ctx, "ghost") == []


# ---------------------------------------------------------------------------
# Plugin — status_lines
# ---------------------------------------------------------------------------


def test_status_lines_count_by_window(tmp_path: Path):
    (tmp_path / "a.py").write_text(
        '@deprecated(since="1.5.0", remove_in="2.0.0")\n'  # due in next 2.0
    )
    (tmp_path / "b.py").write_text(
        '@deprecated(since="2.0.0", remove_in="3.0.0")\n'  # added this release, upcoming
    )
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "1.5.0", "2.0.0")},
        plugin_config={"scan": ["*.py"]},
    )
    lines = DeprecationPlugin().status_lines(ctx)
    assert len(lines) == 1
    assert "due for removal" in lines[0]
    assert "1 added" in lines[0]
    assert "1 upcoming" in lines[0]  # remove_in=3.0 still in future for 2.0 bump


def test_status_lines_empty_when_no_markers(tmp_path: Path):
    """No source files → no markers → no lines."""
    ctx = _make_ctx(
        repo=tmp_path,
        plan_bumps={"api": _planned("api", "1.0.0", "2.0.0")},
        plugin_config={"scan": ["*.py"]},
    )
    assert DeprecationPlugin().status_lines(ctx) == []
