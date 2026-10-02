# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""The planner's ``_direct_pass`` falls back to :meth:`Plugin.affects`
only once plain `paths` matching has already failed to attribute a
commit's files to a component (see :mod:`multicz.plugins.protocol`)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from multicz.config import load_config
from multicz.planner import build_plan
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


def test_build_plan_affects_fallback_for_conventional_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = _init_repo(tmp_path, CONFIG_WITH_PLUGIN)
    plugin = _ClaimsApi()
    monkeypatch.setattr("multicz.plugins.runner.DEFAULT_REGISTRY", PluginRegistry([plugin]))
    _commit(repo, {"README.md": "docs\n"}, "feat: unrelated-looking feature")

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert plan.bumps["api"].kind == "minor"
    assert plugin.calls == [("api", ("README.md",))]


def test_build_plan_affects_fallback_for_non_conventional_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = """
[project]
unknown_commit_policy = "patch"

[plugins.claims-api]

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
"""
    repo = _init_repo(tmp_path, cfg)
    plugin = _ClaimsApi()
    monkeypatch.setattr("multicz.plugins.runner.DEFAULT_REGISTRY", PluginRegistry([plugin]))
    _commit(repo, {"README.md": "docs\n"}, "update unrelated-looking file")

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert plan.bumps["api"].kind == "patch"
    [reason] = plan.bumps["api"].reasons
    assert reason.__class__.__name__ == "NonConventionalReason"
    assert plugin.calls == [("api", ("README.md",))]


def test_build_plan_does_not_consult_plugin_when_path_already_owns_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = _init_repo(tmp_path, CONFIG_WITH_PLUGIN)
    plugin = _ClaimsApi()
    monkeypatch.setattr("multicz.plugins.runner.DEFAULT_REGISTRY", PluginRegistry([plugin]))
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: a path-owned feature")

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert plan.bumps["api"].kind == "minor"
    assert plugin.calls == []
