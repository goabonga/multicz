# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Tests for ``multicz changed``, in particular its ``overlap_policy``
handling: a file several components share must be attributed to every
one of them under ``"all"``, and only the first-declared one otherwise -
the same split :func:`multicz.planner.build._direct_pass` already makes."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _config(policy: str) -> str:
    return f"""
[project]
overlap_policy = "{policy}"

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{{ file = "pyproject.toml", key = "project.version" }}]

[components.lib]
paths = ["src/**"]
bump_files = [{{ file = "pyproject.toml", key = "project.version" }}]
"""


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _init_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: str) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit(
        tmp_path,
        {
            "multicz.toml": _config(policy),
            "pyproject.toml": '[project]\nname = "x"\nversion = "1.0.0"\n',
            "src/main.py": "x = 1\n",
        },
        "chore: init",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_changed_default_policy_reports_only_first_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
):
    repo = _init_repo(tmp_path, monkeypatch, "first-match")
    _commit(repo, {"src/main.py": "x = 2\n"}, "fix: touch the shared path")

    result = runner.invoke(app, ["changed", "--since", "HEAD~1", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["changed"] == ["api"]
    assert data["unchanged"] == ["lib"]


def test_changed_overlap_all_reports_every_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
):
    repo = _init_repo(tmp_path, monkeypatch, "all")
    _commit(repo, {"src/main.py": "x = 2\n"}, "fix: touch the shared path")

    result = runner.invoke(app, ["changed", "--since", "HEAD~1", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert sorted(data["changed"]) == ["api", "lib"]
    assert data["unchanged"] == []


def test_changed_overlap_all_does_not_affect_an_unowned_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
):
    """A file only `api` owns still reports `api` alone under "all" -
    the new branch must not over-match paths nothing else claims."""
    repo = _init_repo(tmp_path, monkeypatch, "all")
    _commit(
        repo,
        {"pyproject.toml": '[project]\nname = "x"\nversion = "1.0.1"\n'},
        "fix: api-only change",
    )

    result = runner.invoke(app, ["changed", "--since", "HEAD~1", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["changed"] == ["api"]
    assert data["unchanged"] == ["lib"]


def test_changed_follows_depends_on_cascade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
):
    """A `depends_on` downstream component shows up in `changed` even
    though none of its own paths were touched - the same cascade
    :func:`multicz.planner.build._triggers_pass` applies at release time.
    Not reachable through ``test_changed_overlap_*`` above: those
    components share a path, this one shares nothing but the edge."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit(
        tmp_path,
        {
            "multicz.toml": """
[components.api]
paths = ["src/api/**"]
bump_files = [{ file = "src/api/version.txt" }]

[components.lib]
paths = ["src/lib/**"]
bump_files = [{ file = "src/lib/version.txt" }]
depends_on = ["api"]
""",
            "src/api/version.txt": "1.0.0",
            "src/lib/version.txt": "1.0.0",
        },
        "chore: init",
    )
    monkeypatch.chdir(tmp_path)
    _commit(tmp_path, {"src/api/version.txt": "1.0.0\n"}, "fix: touch api only")

    result = runner.invoke(app, ["changed", "--since", "HEAD~1", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert sorted(data["changed"]) == ["api", "lib"]
    assert data["unchanged"] == []
