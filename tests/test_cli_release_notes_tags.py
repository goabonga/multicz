# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz release-notes``: past tags with siblings, error paths."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app

CONFIG = """
[components.lib]
paths = ["lib/**"]
bump_files = [{ file = "lib/v.toml", key = "version" }]

[components.app]
paths = ["app/**"]
depends_on = ["lib"]
bump_files = [{ file = "app/v.toml", key = "version" }]
"""


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout


def _commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit(
        tmp_path,
        {
            "multicz.toml": CONFIG,
            "lib/v.toml": 'version = "1.0.0"\n',
            "app/v.toml": 'version = "2.0.0"\n',
        },
        "chore: init",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def released(repo: Path) -> Path:
    _commit(repo, {"lib/code.py": "x = 1\n"}, "feat(lib): add thing")
    result = CliRunner().invoke(app, ["bump", "--commit", "--tag"])
    assert result.exit_code == 0, result.output
    return repo


def test_tag_notes_pick_up_depends_on_cascade(released: Path):
    # An unrelated tag on the same release commit is ignored.
    _git(released, "tag", "unrelated-marker")
    result = CliRunner().invoke(app, ["release-notes", "--tag", "app-v2.0.1"])
    assert result.exit_code == 0, result.output
    assert "lib" in result.output
    assert "1.1.0" in result.output


def test_tag_notes_for_unknown_tag_fails(released: Path):
    result = CliRunner().invoke(app, ["release-notes", "--tag", "nothing-v1.0.0"])
    assert result.exit_code == 1
    assert "doesn't match any component" in result.output


def test_tag_is_exclusive_with_component(released: Path):
    result = CliRunner().invoke(app, ["release-notes", "lib", "--tag", "lib-v1.1.0"])
    assert result.exit_code == 1
    assert "exclusive" in result.output


def test_requires_a_target(released: Path):
    result = CliRunner().invoke(app, ["release-notes"])
    assert result.exit_code == 1
    assert "specify a component" in result.output


def test_unknown_component(released: Path):
    result = CliRunner().invoke(app, ["release-notes", "nope"])
    assert result.exit_code == 1
    assert "unknown component" in result.output


def test_component_without_pending_bump(released: Path):
    result = CliRunner().invoke(app, ["release-notes", "lib"])
    assert result.exit_code == 0, result.output
    assert "no pending bump for lib" in result.output


def test_all_with_nothing_pending_is_empty(released: Path):
    result = CliRunner().invoke(app, ["release-notes", "--all"])
    assert result.exit_code == 0, result.output
    assert "nothing to release" in result.output


def test_prerelease_tag_uses_previous_tag(released: Path):
    _commit(released, {"lib/code.py": "x = 2\n"}, "feat(lib): more")
    result = CliRunner().invoke(app, ["bump", "--commit", "--tag", "--pre", "rc"])
    assert result.exit_code == 0, result.output
    tag = _git(released, "tag", "--list", "lib-v*rc*").split()[0]
    notes = CliRunner().invoke(app, ["release-notes", "--tag", tag])
    assert notes.exit_code == 0, notes.output
    assert "more" in notes.output
