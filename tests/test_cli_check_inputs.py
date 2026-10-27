# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz check``: stdin input and config-less fallback."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app


def test_check_reads_message_from_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["check", "-"], input="feat: add thing\n")
    assert result.exit_code == 0, result.output


def test_check_rejects_invalid_stdin_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["check", "-"], input="not conventional\n")
    assert result.exit_code == 1
    assert "invalid commit message" in result.output


def test_check_falls_back_to_default_types_on_bad_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "multicz.toml").write_text(
        '[components.api]\npaths = ["a/**"]\ndepends_on = ["x"]\n'
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["check", "-"], input="fix: ok\n")
    assert result.exit_code == 0, result.output
