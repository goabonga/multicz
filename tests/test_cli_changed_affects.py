# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz changed`` falls back to :meth:`Plugin.affects` only once
plain `paths` matching has already failed to claim a component for a
change (see :mod:`multicz.plugins.protocol`)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app
from multicz.plugins import BasePlugin, PluginRegistry


class _ClaimsApi(BasePlugin):
    """Test double: claims ``api`` for any path, records every call."""

    name = "claims-api"

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def affects(self, ctx, component, paths):
        self.calls.append((component, tuple(paths)))
        return component == "api"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _init_repo(tmp_path: Path, config: str) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit(
        tmp_path,
        {
            "multicz.toml": config,
            "pyproject.toml": '[project]\nname = "x"\nversion = "1.0.0"\n',
            "src/main.py": "x = 1\n",
        },
        "chore: init",
    )
    return tmp_path


CONFIG_WITH_PLUGIN = """
[plugins.claims-api]

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
"""

CONFIG_WITHOUT_PLUGIN = """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
"""


def test_changed_claims_component_via_plugin_when_paths_dont_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = _init_repo(tmp_path, CONFIG_WITH_PLUGIN)
    plugin = _ClaimsApi()
    monkeypatch.setattr("multicz.plugins.runner.DEFAULT_REGISTRY", PluginRegistry([plugin]))
    monkeypatch.chdir(repo)
    _commit(repo, {"README.md": "docs\n"}, "fix: unrelated-looking change")

    result = CliRunner().invoke(app, ["changed", "--since", "HEAD~1", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["changed"] == ["api"]
    assert plugin.calls == [("api", ("README.md",))]


def test_changed_skips_plugin_once_path_matching_already_claims_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """``owns_path or run_affects(...)`` short-circuits - a plugin is
    pure overhead once a path already settles ownership."""
    repo = _init_repo(tmp_path, CONFIG_WITH_PLUGIN)
    plugin = _ClaimsApi()
    monkeypatch.setattr("multicz.plugins.runner.DEFAULT_REGISTRY", PluginRegistry([plugin]))
    monkeypatch.chdir(repo)
    _commit(repo, {"src/main.py": "x = 2\n"}, "fix: a path-owned change")

    result = CliRunner().invoke(app, ["changed", "--since", "HEAD~1", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["changed"] == ["api"]
    assert plugin.calls == []


def test_changed_inactive_plugin_is_never_consulted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Without ``[plugins.claims-api]`` opting it in, the plugin must
    not be able to claim ownership of an otherwise-unowned path."""
    repo = _init_repo(tmp_path, CONFIG_WITHOUT_PLUGIN)
    plugin = _ClaimsApi()
    monkeypatch.setattr("multicz.plugins.runner.DEFAULT_REGISTRY", PluginRegistry([plugin]))
    monkeypatch.chdir(repo)
    _commit(repo, {"README.md": "docs\n"}, "fix: unrelated-looking change")

    result = CliRunner().invoke(app, ["changed", "--since", "HEAD~1", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["changed"] == []
    assert plugin.calls == []
