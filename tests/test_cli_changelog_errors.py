# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz changelog``: unknown component."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app

CONFIG = """
[components.api]
paths = ["src/**"]
bump_files = [{ file = "src/v.toml", key = "version" }]
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "multicz.toml").write_text(CONFIG)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "v.toml").write_text('version = "1.0.0"\n')
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "chore: init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_changelog_unknown_component_fails(repo: Path):
    result = CliRunner().invoke(app, ["changelog", "--component", "ghost"])
    assert result.exit_code == 1
    assert "unknown component" in result.output
