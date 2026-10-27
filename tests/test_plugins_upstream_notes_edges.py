# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Upstream-notes plugin edge cases: odd tag listings, missing or empty
upstream windows."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from multicz.plugins import PluginContext
from multicz.plugins.builtin.upstream_notes import UpstreamNotesPlugin
from multicz.plugins.builtin.upstream_notes import plugin as notes


def _git(cwd: Path, *args: str) -> None:
    env = {
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@e",
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, check=True)


def _commit(cwd: Path, message: str) -> None:
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-m", message)


def _component(paths: list[str], depends_on: list[str] | None = None):
    return SimpleNamespace(paths=paths, exclude_paths=[], depends_on=depends_on or [])


def _ctx(repo: Path) -> PluginContext:
    config = SimpleNamespace(
        components={
            "config": _component(["config/**"], ["root"]),
            "root": _component(["root/**"]),
        },
        project=SimpleNamespace(release_commit_pattern=r"^chore\(release\)"),
        tag_format_for=lambda name: "{component}-v{version}",
        ignored_types_for=lambda name: set(),
    )
    bumps = {
        "config": SimpleNamespace(component="config", current="1.0.0", next="1.1.0"),
    }
    plan = type("FakePlan", (), {"bumps": bumps})()
    return PluginContext(config=config, repo=repo, plan=plan, plugin_config={})


def test_highest_tag_merged_skips_foreign_and_invalid_tags(monkeypatch: pytest.MonkeyPatch):
    listing = "other-v9.9.9\nroot-vnot-a-version\nroot-v1.0.0\nroot-v1.2.0\n"
    monkeypatch.setattr(notes, "_git", lambda args, cwd: listing)
    assert notes._highest_tag_merged(Path("."), "root-v", "HEAD") == "root-v1.2.0"


def test_upstream_without_any_tag_yields_nothing(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "a").write_text("1\n")
    _commit(tmp_path, "chore: seed")
    _git(tmp_path, "tag", "config-v1.0.0")

    assert UpstreamNotesPlugin().enrich_changelog(_ctx(tmp_path), "config") == []


def test_upstream_window_without_owned_commits_yields_nothing(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "config").mkdir()
    (tmp_path / "root").mkdir()
    (tmp_path / "config" / "a").write_text("1\n")
    (tmp_path / "root" / "a").write_text("1\n")
    _commit(tmp_path, "chore: seed")
    _git(tmp_path, "tag", "root-v1.0.0")
    _git(tmp_path, "tag", "config-v1.0.0")
    # The only commit between the two upstream tags touches config/ only.
    (tmp_path / "config" / "a").write_text("2\n")
    _commit(tmp_path, "feat: config only")
    _git(tmp_path, "tag", "root-v1.1.0")

    assert UpstreamNotesPlugin().enrich_changelog(_ctx(tmp_path), "config") == []
