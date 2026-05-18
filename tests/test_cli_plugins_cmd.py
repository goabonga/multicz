# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz plugins`` command — listing + JSON output."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app

MINIMAL_CONFIG = """\
[project]
commit_convention = "conventional"

[components.api]
paths = ["src/**"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
"""


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Tiny git repo with a multicz.toml — enough for `_load` to succeed."""
    (tmp_path / "multicz.toml").write_text(MINIMAL_CONFIG)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.0.0"\n'
    )
    for args in (
        ("init", "-q"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "Test"),
        ("add", "-A"),
        ("commit", "-q", "-m", "init"),
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_plugins_command_lists_builtin_deprecation(repo: Path, runner: CliRunner):
    """The built-in deprecation plugin is registered via multicz's own
    entry point, so a vanilla install must surface it."""
    result = runner.invoke(app, ["plugins"])
    assert result.exit_code == 0, result.stdout
    assert "deprecation" in result.stdout


def test_plugins_command_json_shape(repo: Path, runner: CliRunner):
    """Without an explicit ``[plugins.deprecation]`` section the plugin
    is shown as discovered-but-inactive: it would not run, even though
    multicz ships it. Opt-in is explicit."""
    result = runner.invoke(app, ["plugins", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "plugins" in payload
    names = {p["name"] for p in payload["plugins"]}
    assert "deprecation" in names
    dep = next(p for p in payload["plugins"] if p["name"] == "deprecation")
    assert dep["status"] == "inactive"
    assert dep["configured"] is False
    assert dep["enabled"] is False
    assert dep["module"].startswith("multicz.plugins.builtin.deprecation")
    assert dep["class"] == "DeprecationPlugin"
    assert dep["config"] == {}


def test_plugins_command_active_when_section_declared_empty(
    repo: Path, runner: CliRunner
):
    """An empty ``[plugins.deprecation]`` is the minimal opt-in — the
    plugin must flip to ``active`` even without any keys under it."""
    (repo / "multicz.toml").write_text(
        MINIMAL_CONFIG + "\n[plugins.deprecation]\n"
    )
    result = runner.invoke(app, ["plugins", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    dep = next(p for p in payload["plugins"] if p["name"] == "deprecation")
    assert dep["status"] == "active"
    assert dep["configured"] is True
    assert dep["enabled"] is True
    assert dep["config"] == {}


def test_plugins_command_reflects_disabled_state(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(
        MINIMAL_CONFIG
        + "\n[plugins.deprecation]\nenabled = false\n"
        "scan = [\"src/**/*.py\"]\n"
    )
    result = runner.invoke(app, ["plugins", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    dep = next(p for p in payload["plugins"] if p["name"] == "deprecation")
    assert dep["status"] == "disabled"
    assert dep["configured"] is True
    assert dep["enabled"] is False
    assert dep["config"] == {"enabled": False, "scan": ["src/**/*.py"]}


def test_plugins_command_text_output_mentions_disabled(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(
        MINIMAL_CONFIG + "\n[plugins.deprecation]\nenabled = false\n"
    )
    result = runner.invoke(app, ["plugins"])
    assert result.exit_code == 0
    assert "deprecation" in result.stdout
    assert "disabled" in result.stdout


def test_plugins_command_text_output_mentions_inactive(repo: Path, runner: CliRunner):
    """Default install with no ``[plugins.*]`` sections — the table must
    surface ``inactive`` so users know the plugin won't run unless they
    opt in."""
    result = runner.invoke(app, ["plugins"])
    assert result.exit_code == 0
    assert "deprecation" in result.stdout
    assert "inactive" in result.stdout
