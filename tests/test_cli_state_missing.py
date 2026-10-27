# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz state``: configured state file that does not exist yet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app

CONFIG = """
[project]
state_file = ".multicz/state.json"

[components.api]
paths = ["src/**"]
bump_files = [{ file = "v.toml", key = "version" }]
"""


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "multicz.toml").write_text(CONFIG)
    (tmp_path / "v.toml").write_text('version = "1.2.0"\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_state_missing_file_text(repo: Path):
    result = CliRunner().invoke(app, ["state"])
    assert result.exit_code == 0, result.output
    assert ".multicz/state.json" in result.output


def test_state_missing_file_json(repo: Path):
    result = CliRunner().invoke(app, ["state", "--output", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) is None
