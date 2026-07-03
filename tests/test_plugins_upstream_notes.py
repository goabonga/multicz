# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Built-in upstream-notes plugin — upstream resolution + enrich_changelog
+ status_lines."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from multicz.plugins import PluginContext
from multicz.plugins.builtin.upstream_notes import UpstreamNotesPlugin

# ---------------------------------------------------------------------------
# Git-repo fixture
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str, env: dict | None = None) -> str:
    """Run git deterministically — fixed author/committer identity so
    commit SHAs would be reproducible across machines if they were ever
    compared."""
    baseline = {
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@e",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    }
    if env:
        baseline.update(env)
    r = subprocess.run(
        ["git", *args], cwd=cwd, env={**baseline, "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, check=True,
    )
    return r.stdout


def _commit(cwd: Path, message: str) -> str:
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-m", message)
    return _git(cwd, "rev-parse", "HEAD").strip()


@pytest.fixture
def upstream_repo(tmp_path: Path) -> Path:
    """Build a repo shaped like the plugin's target use-case:

    * ``root`` component owns ``root/**``
    * ``config`` component owns ``config/**`` and depends on ``root``
    * tags in order: ``root-v1.0.0`` (empty seed) → feat under ``root/``
      + ``root-v1.1.0`` → ``config-v1.0.0`` at that HEAD → feat under
      ``root/`` + ``root-v1.2.0`` → deploy commit under ``config/``.

    Plan says ``config`` is about to bump ``1.0.0 → 1.1.0``. The plugin
    should therefore ship the two upstream commits that landed *after*
    ``config-v1.0.0``.
    """
    _git(tmp_path, "init", "-q")
    (tmp_path / "root").mkdir()
    (tmp_path / "config").mkdir()

    (tmp_path / "root" / "main.tf").write_text("v0\n")
    (tmp_path / "config" / "main.tf").write_text("v0\n")
    _commit(tmp_path, "chore: seed")
    _git(tmp_path, "tag", "root-v1.0.0")

    (tmp_path / "root" / "main.tf").write_text("private endpoint\n")
    _commit(tmp_path, "feat(network): add private endpoint subnet")
    _git(tmp_path, "tag", "root-v1.1.0")

    _git(tmp_path, "tag", "config-v1.0.0")

    (tmp_path / "root" / "main.tf").write_text("pin provider\n")
    _commit(tmp_path, "fix: pin azurerm provider")
    _git(tmp_path, "tag", "root-v1.2.0")

    (tmp_path / "config" / "main.tf").write_text("deploy new endpoint\n")
    _commit(tmp_path, "deploy: apply root-v1.2.0")
    return tmp_path


# ---------------------------------------------------------------------------
# Config + Plan stubs
# ---------------------------------------------------------------------------


def _component(*, paths: list[str], depends_on: list[str] | None = None):
    """Minimal duck-typed component. ``ComponentMatcher`` needs ``paths``
    and ``exclude_paths``; the plugin also reads ``depends_on``."""
    return SimpleNamespace(
        paths=paths, exclude_paths=[], depends_on=depends_on or [],
    )


def _config(components: dict, *, release_pattern: str = r"^chore\(release\)",
            ignored_types: dict[str, set[str]] | None = None) -> SimpleNamespace:
    ignored_types = ignored_types or {}

    return SimpleNamespace(
        components=components,
        project=SimpleNamespace(release_commit_pattern=release_pattern),
        tag_format_for=lambda name: "{component}-v{version}",
        ignored_types_for=lambda name: ignored_types.get(name, set()),
    )


def _planned(component: str, current: str, next_version: str):
    """Stand-in ``PlannedBump`` — the plugin only reads
    ``component`` / ``current`` / ``next``."""
    return SimpleNamespace(component=component, current=current, next=next_version)


def _ctx(repo: Path, config, bumps: dict, plugin_config: dict | None = None):
    plan = type("FakePlan", (), {"bumps": bumps})()
    return PluginContext(
        config=config, repo=repo, plan=plan, plugin_config=plugin_config or {},
    )


# ---------------------------------------------------------------------------
# _upstreams_for — explicit mapping vs depends_on transitive closure
# ---------------------------------------------------------------------------


def test_upstreams_for_uses_explicit_mapping_first(tmp_path: Path):
    """When ``[plugins.upstream-notes.upstreams]`` names the upstreams
    explicitly, the ``depends_on`` graph is ignored."""
    plugin = UpstreamNotesPlugin()
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["root"]),
        "root": _component(paths=["root/**"]),
        "explicit": _component(paths=["explicit/**"]),
    })
    ctx = _ctx(
        tmp_path, cfg, bumps={},
        plugin_config={"upstreams": {"config": ["explicit"]}},
    )
    assert plugin._upstreams_for(ctx, "config") == ["explicit"]


def test_upstreams_for_filters_unknown_names_from_mapping(tmp_path: Path):
    """A mapping to a component that doesn't exist in the config is
    silently dropped — a typo doesn't crash the bump."""
    plugin = UpstreamNotesPlugin()
    cfg = _config({
        "config": _component(paths=["config/**"]),
        "root": _component(paths=["root/**"]),
    })
    ctx = _ctx(
        tmp_path, cfg, bumps={},
        plugin_config={"upstreams": {"config": ["root", "typo"]}},
    )
    assert plugin._upstreams_for(ctx, "config") == ["root"]


def test_upstreams_for_walks_depends_on_transitively(tmp_path: Path):
    """No explicit mapping → walk the ``depends_on`` graph. ``config``
    depends on ``root``, which itself depends on ``module`` — both must
    surface."""
    plugin = UpstreamNotesPlugin()
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["root"]),
        "root": _component(paths=["root/**"], depends_on=["module"]),
        "module": _component(paths=["module/**"]),
    })
    ctx = _ctx(tmp_path, cfg, bumps={})
    assert plugin._upstreams_for(ctx, "config") == ["root", "module"]


def test_upstreams_for_ignores_self_cycle(tmp_path: Path):
    """A component that lists itself as an upstream is skipped rather
    than looping forever."""
    plugin = UpstreamNotesPlugin()
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["config", "root"]),
        "root": _component(paths=["root/**"]),
    })
    ctx = _ctx(tmp_path, cfg, bumps={})
    assert plugin._upstreams_for(ctx, "config") == ["root"]


# ---------------------------------------------------------------------------
# enrich_changelog — happy path + early exits
# ---------------------------------------------------------------------------


def test_enrich_changelog_returns_empty_when_component_not_in_plan(
    upstream_repo: Path,
):
    plugin = UpstreamNotesPlugin()
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["root"]),
        "root": _component(paths=["root/**"]),
    })
    ctx = _ctx(upstream_repo, cfg, bumps={})  # empty plan
    assert plugin.enrich_changelog(ctx, "config") == []


def test_enrich_changelog_returns_empty_when_no_upstreams(upstream_repo: Path):
    """A component with no ``depends_on`` and no explicit mapping has
    nothing to enrich."""
    plugin = UpstreamNotesPlugin()
    cfg = _config({
        "config": _component(paths=["config/**"]),
    })
    ctx = _ctx(
        upstream_repo, cfg,
        bumps={"config": _planned("config", "1.0.0", "1.1.0")},
    )
    assert plugin.enrich_changelog(ctx, "config") == []


def test_enrich_changelog_emits_section_for_upstream_drift(upstream_repo: Path):
    """The core acceptance test: ``config-v1.0.0`` was cut when
    ``root-v1.1.0`` was the head; ``root-v1.2.0`` landed after. The
    plugin must ship one Upstream section listing the commits between
    those two upstream tags."""
    plugin = UpstreamNotesPlugin()
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["root"]),
        "root": _component(paths=["root/**"]),
    })
    ctx = _ctx(
        upstream_repo, cfg,
        bumps={"config": _planned("config", "1.0.0", "1.1.0")},
    )
    entries = plugin.enrich_changelog(ctx, "config")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.section == "Upstream: root (v1.1.0 → v1.2.0)"
    assert entry.component == "config"
    assert len(entry.lines) == 1
    assert entry.lines[0].startswith("- fix: pin azurerm provider (")


def test_enrich_changelog_skips_upstream_when_head_equals_baseline(
    upstream_repo: Path,
):
    """No upstream tag after the baseline → nothing to say. The plugin
    must return an empty list, not emit an empty section."""
    plugin = UpstreamNotesPlugin()
    # Delete the post-baseline upstream tag so the baseline is already at HEAD
    # for root.
    subprocess.run(
        ["git", "tag", "-d", "root-v1.2.0"], cwd=upstream_repo, check=True,
    )
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["root"]),
        "root": _component(paths=["root/**"]),
    })
    ctx = _ctx(
        upstream_repo, cfg,
        bumps={"config": _planned("config", "1.0.0", "1.1.0")},
    )
    assert plugin.enrich_changelog(ctx, "config") == []


def test_enrich_changelog_with_no_baseline_tag_still_emits(upstream_repo: Path):
    """First release of the downstream component — no baseline tag
    exists yet. The plugin must still surface upstream commits, with the
    section labelled ``v∅ → v<head>``."""
    plugin = UpstreamNotesPlugin()
    subprocess.run(
        ["git", "tag", "-d", "config-v1.0.0"], cwd=upstream_repo, check=True,
    )
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["root"]),
        "root": _component(paths=["root/**"]),
    })
    ctx = _ctx(
        upstream_repo, cfg,
        bumps={"config": _planned("config", "0.0.0", "1.0.0")},
    )
    entries = plugin.enrich_changelog(ctx, "config")
    assert len(entries) == 1
    assert entries[0].section == "Upstream: root (v∅ → v1.2.0)"
    # Both upstream commits (feat + fix) are surfaced because there's no
    # baseline to bound the range.
    assert len(entries[0].lines) == 2


def test_enrich_changelog_truncates_with_max_commits(upstream_repo: Path):
    """``max_commits`` caps the bullet list and appends an ellipsis
    line reporting how many were dropped."""
    plugin = UpstreamNotesPlugin()
    subprocess.run(
        ["git", "tag", "-d", "config-v1.0.0"], cwd=upstream_repo, check=True,
    )
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["root"]),
        "root": _component(paths=["root/**"]),
    })
    ctx = _ctx(
        upstream_repo, cfg,
        bumps={"config": _planned("config", "0.0.0", "1.0.0")},
        plugin_config={"max_commits": 1},
    )
    entries = plugin.enrich_changelog(ctx, "config")
    lines = entries[0].lines
    assert len(lines) == 2
    assert lines[-1] == "- … and 1 more"


def test_enrich_changelog_ignores_release_and_ignored_commits(upstream_repo: Path):
    """Both the ``release_commit_pattern`` and per-upstream
    ``ignored_types_for`` are applied to the commit filter."""
    plugin = UpstreamNotesPlugin()
    subprocess.run(
        ["git", "tag", "-d", "config-v1.0.0"], cwd=upstream_repo, check=True,
    )
    cfg = _config(
        {
            "config": _component(paths=["config/**"], depends_on=["root"]),
            "root": _component(paths=["root/**"]),
        },
        ignored_types={"root": {"fix"}},
    )
    ctx = _ctx(
        upstream_repo, cfg,
        bumps={"config": _planned("config", "0.0.0", "1.0.0")},
    )
    entries = plugin.enrich_changelog(ctx, "config")
    # Only the ``feat(network): ...`` commit survives — ``fix: ...`` is ignored.
    assert len(entries[0].lines) == 1
    assert "feat(network)" in entries[0].lines[0]


# ---------------------------------------------------------------------------
# status_lines
# ---------------------------------------------------------------------------


def test_status_lines_reports_pending_upstream_drift(upstream_repo: Path):
    plugin = UpstreamNotesPlugin()
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["root"]),
        "root": _component(paths=["root/**"]),
    })
    ctx = _ctx(
        upstream_repo, cfg,
        bumps={"config": _planned("config", "1.0.0", "1.1.0")},
    )
    lines = plugin.status_lines(ctx)
    assert len(lines) == 1
    assert "config: ships 1 upstream change" in lines[0]
    assert "Upstream: root (v1.1.0 → v1.2.0)" in lines[0]


def test_status_lines_empty_when_no_drift(upstream_repo: Path):
    plugin = UpstreamNotesPlugin()
    subprocess.run(
        ["git", "tag", "-d", "root-v1.2.0"], cwd=upstream_repo, check=True,
    )
    cfg = _config({
        "config": _component(paths=["config/**"], depends_on=["root"]),
        "root": _component(paths=["root/**"]),
    })
    ctx = _ctx(
        upstream_repo, cfg,
        bumps={"config": _planned("config", "1.0.0", "1.1.0")},
    )
    assert plugin.status_lines(ctx) == []
