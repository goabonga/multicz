# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz get``: error paths and the explicit ``version`` field."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app

CONFIG = """
[components.api]
paths = ["src/**"]
bump_files = [{ file = "v.toml", key = "version" }]

[components.bare]
paths = ["bare/**"]
"""


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "multicz.toml").write_text(CONFIG)
    (tmp_path / "v.toml").write_text('version = "1.2.0"\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_get_unknown_component(repo: Path):
    result = CliRunner().invoke(app, ["get", "ghost"])
    assert result.exit_code == 1
    assert "unknown component" in result.output


def test_get_component_without_bump_files(repo: Path):
    result = CliRunner().invoke(app, ["get", "bare"])
    assert result.exit_code == 1
    assert "has no bump_files" in result.output


def test_get_unsupported_field(repo: Path):
    result = CliRunner().invoke(app, ["get", "api.image_tag"])
    assert result.exit_code == 1
    assert "unsupported field" in result.output


def test_get_explicit_version_field(repo: Path):
    result = CliRunner().invoke(app, ["get", "api.version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "1.2.0"
