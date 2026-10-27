# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Shared CLI helpers: config loading errors and cascade entry building."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from multicz.cli import app
from multicz.cli._shared import _cascade_entries_for
from multicz.planner import MirrorReason, TriggerReason


def test_missing_config_exits_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 1
    assert "Traceback" not in result.output


def test_schema_error_lists_each_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "multicz.toml").write_text('[components.api]\npaths = "not-a-list"\n')
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 1
    assert "invalid" in result.output
    assert "components" in result.output


def test_reference_error_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "multicz.toml").write_text(
        '[components.api]\npaths = ["a/**"]\ndepends_on = ["ghost"]\n'
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 1
    assert "invalid" in result.output
    assert "ghost" in result.output


def _plan(*bumps: str) -> SimpleNamespace:
    return SimpleNamespace(bumps={name: SimpleNamespace(next="2.0.0") for name in bumps})


def test_cascade_entries_dedup_upstream_and_skip_unplanned():
    reasons = [
        object(),
        MirrorReason(upstream="api", file="a.yaml", key="k"),
        TriggerReason(upstream="api", upstream_kind="minor"),
        TriggerReason(upstream="ghost", upstream_kind="minor"),
    ]
    planned = SimpleNamespace(reasons=reasons)
    config = SimpleNamespace(components={})
    entries = _cascade_entries_for(planned, _plan("api"), config)
    assert [(e.upstream, e.upstream_version) for e in entries] == [("api", "2.0.0")]
