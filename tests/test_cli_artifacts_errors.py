# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz artifacts``: argument conflicts and unknown component."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app

CONFIG = """
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


def test_all_is_exclusive_with_a_component(repo: Path):
    result = CliRunner().invoke(app, ["artifacts", "api", "--all"])
    assert result.exit_code == 1
    assert "exclusive" in result.output


def test_unknown_component(repo: Path):
    result = CliRunner().invoke(app, ["artifacts", "ghost"])
    assert result.exit_code == 1
    assert "unknown component" in result.output
