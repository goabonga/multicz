"""Fixtures shared by all scenario tests.

Scenarios describe end-to-end usage of multicz — a fixture repo, some
git activity, then a CLI invocation whose output is asserted against
user-visible behaviour. They exist alongside the unit tests as a
*functional contract*: a regression in a scenario means user-visible
behaviour has shifted, even if no individual unit test broke.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def make_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[dict[str, str]], Path]:
    """Build a git repo from a dict of relative paths -> file content.

    Initialises git, sets a stable author, stages every file, makes a
    single ``chore: init`` commit, and chdir's into the repo so the
    subsequent CLI invocations find ``multicz.toml`` (or its inlined
    equivalent) automatically.
    """

    def _make(files: dict[str, str]) -> Path:
        for name, content in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        _git(tmp_path, "init", "-q", "-b", "main")
        _git(tmp_path, "config", "user.email", "scenarios@multicz")
        _git(tmp_path, "config", "user.name", "scenarios")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "chore: init")
        monkeypatch.chdir(tmp_path)
        return tmp_path

    return _make


@pytest.fixture
def commit(tmp_path: Path) -> Callable[..., str]:
    """Stage updates to one or more files, commit them, return the new SHA."""

    def _commit(files: dict[str, str], message: str) -> str:
        for name, content in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", message)
        return _git(tmp_path, "rev-parse", "HEAD").strip()

    return _commit


@pytest.fixture
def git(tmp_path: Path) -> Callable[..., str]:
    """Direct passthrough to git for scenario-specific operations
    (creating tags, inspecting history, etc.)."""

    def _git_passthrough(*args: str) -> str:
        return _git(tmp_path, *args)

    return _git_passthrough
