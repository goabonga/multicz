# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""The changelog, ``changelog`` and ``release-notes`` attribute commits
exactly like the planner: path globs first (every match under
``overlap_policy = "all"``), then an active plugin's ``affects``. A commit
that bumps a component therefore always shows up in its release notes."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app
from multicz.config import ComponentMatcher, load_config
from multicz.planner import owned_files
from multicz.plugins import BasePlugin, PluginRegistry


class _ClaimsApi(BasePlugin):
    """Test double: claims ``api`` for any path (like an import graph would)."""

    name = "claims-api"

    def affects(self, ctx, component, paths):
        return component == "api"


CONFIG = """
[project]
overlap_policy = "all"

[plugins.claims-api]

[components.api]
paths = ["src/**", "pyproject.toml", "Makefile"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
changelog = "CHANGELOG.md"

[components.web]
paths = ["web/**", "Makefile"]
bump_files = [{ file = "web/package.toml", key = "version" }]
changelog = "web/CHANGELOG.md"
"""

INITIAL = {
    "multicz.toml": CONFIG,
    "pyproject.toml": '[project]\nname = "x"\nversion = "1.0.0"\n',
    "web/package.toml": 'version = "2.0.0"\n',
    "src/main.py": "x = 1\n",
    "web/app.js": "1\n",
    "Makefile": "all:\n",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


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
    _commit(tmp_path, INITIAL, "chore: init")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "multicz.plugins.runner.DEFAULT_REGISTRY", PluginRegistry([_ClaimsApi()])
    )
    return tmp_path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_owned_files_matches_every_component_under_overlap_all(repo: Path):
    config = load_config(repo / "multicz.toml")
    matcher = ComponentMatcher(config.components)
    assert owned_files(config, repo, matcher, "api", ["Makefile"]) == ("Makefile",)
    assert owned_files(config, repo, matcher, "web", ["Makefile"]) == ("Makefile",)


def test_owned_files_keeps_first_match_without_overlap_all(repo: Path):
    config = load_config(repo / "multicz.toml")
    config.project.overlap_policy = "first-match"
    matcher = ComponentMatcher(config.components)
    assert owned_files(config, repo, matcher, "api", ["Makefile"]) == ("Makefile",)
    assert owned_files(config, repo, matcher, "web", ["Makefile"]) == ()


def test_owned_files_falls_back_to_plugins_only_when_no_path_matches(repo: Path):
    config = load_config(repo / "multicz.toml")
    matcher = ComponentMatcher(config.components)
    files = ["internal/transport/socket.go", "README.md"]
    assert owned_files(config, repo, matcher, "api", files) == tuple(files)
    assert owned_files(config, repo, matcher, "web", files) == ()
    assert owned_files(config, repo, matcher, "api", []) == ()


def test_bump_changelog_lists_a_plugin_attributed_commit(repo: Path, runner: CliRunner):
    socket = "internal/transport/socket.go"
    _commit(repo, {socket: "package t\n"}, "refactor(transport): rework socket")
    _commit(repo, {socket: "package t // x\n"}, "fix(transport): close socket")

    result = runner.invoke(app, ["bump", "--commit", "--tag"])
    assert result.exit_code == 0, result.stdout

    changelog = (repo / "CHANGELOG.md").read_text()
    assert "No notable changes" not in changelog
    assert "**transport**: close socket" in changelog
    assert not (repo / "web/CHANGELOG.md").exists()


def test_bump_changelog_lists_a_shared_file_commit_for_every_owner(repo: Path, runner: CliRunner):
    _commit(repo, {"Makefile": "all: build\n"}, "fix(build): add build target")

    result = runner.invoke(app, ["bump", "--commit", "--tag"])
    assert result.exit_code == 0, result.stdout

    for changelog in ("CHANGELOG.md", "web/CHANGELOG.md"):
        text = (repo / changelog).read_text()
        assert "**build**: add build target" in text, changelog


def test_changelog_command_lists_a_plugin_attributed_commit(repo: Path, runner: CliRunner):
    _commit(repo, {"internal/transport/socket.go": "package t\n"}, "fix(transport): close socket")

    result = runner.invoke(app, ["changelog", "--output", "md", "--component", "api"])
    assert result.exit_code == 0, result.stdout
    assert "close socket" in result.stdout


def test_release_notes_for_a_tag_list_a_plugin_attributed_commit(repo: Path, runner: CliRunner):
    _commit(repo, {"internal/transport/socket.go": "package t\n"}, "fix(transport): close socket")
    assert runner.invoke(app, ["bump", "--commit", "--tag"]).exit_code == 0

    result = runner.invoke(app, ["release-notes", "--tag", "api-v1.0.1"])
    assert result.exit_code == 0, result.stdout
    assert "close socket" in result.stdout
    assert "No notable changes" not in result.stdout
