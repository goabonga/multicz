# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz plan`` surfaces plugin violations and advice."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app

CONFIG = """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[plugins.deprecation]
mode = "warning"
scan = ["src/*.py"]
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


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
            "pyproject.toml": '[project]\nname = "x"\nversion = "1.2.0"\n',
            "src/main.py": "x = 1\n",
        },
        "chore: init",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_plan_prints_plugin_violations_and_advice(repo: Path):
    _commit(
        repo,
        {"src/main.py": "# DEPRECATED since=1.0.0 remove_in=1.3.0 - use y\nx = 2\n"},
        "feat: add stuff",
    )
    result = CliRunner().invoke(app, ["plan"])
    assert result.exit_code == 0, result.output
    assert "must be removed by 1.3.0" in result.output
    assert "1 due for removal" in result.output


def test_plan_pre_and_finalize_are_mutually_exclusive(repo: Path):
    result = CliRunner().invoke(app, ["plan", "--pre", "rc", "--finalize"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_plan_summary_appends_markdown(repo: Path, tmp_path_factory: pytest.TempPathFactory):
    summary = tmp_path_factory.mktemp("summary") / "summary.md"
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add stuff")
    result = CliRunner().invoke(app, ["plan", "--summary", str(summary)])
    assert result.exit_code == 0, result.output
    assert "## Release plan" in summary.read_text()


def test_plan_force_bumps_without_commits(repo: Path):
    result = CliRunner().invoke(app, ["plan", "--force", "api:patch"])
    assert result.exit_code == 0, result.output
    assert "1.2.0 → 1.2.1" in result.output
