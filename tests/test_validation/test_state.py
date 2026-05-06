# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for StateDriftCheck in isolation."""

from __future__ import annotations

from pathlib import Path

from multicz.config import ComponentMatcher, load_config
from multicz.validation._base import ValidationContext
from multicz.validation.state import StateDriftCheck


def _ctx(repo: Path) -> ValidationContext:
    config = load_config(repo / "multicz.toml")
    return ValidationContext(
        repo=repo, config=config, matcher=ComponentMatcher(config.components)
    )


def _write_state(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_state_drift_yields_warning(tmp_path: Path):
    # pyproject says 2.0.0 but state still records 1.0.0
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "2.0.0"\n'
    )
    _write_state(
        tmp_path / ".multicz" / "state.json",
        '{"version": 1, "components": {"api": {"version": "1.0.0"}}}\n',
    )
    (tmp_path / "multicz.toml").write_text("""
[project]
state_file = ".multicz/state.json"

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    findings = list(StateDriftCheck().run(_ctx(tmp_path)))
    drift = [f for f in findings if f.check == "state_drift"]
    assert drift
    assert drift[0].level == "warning"
    assert drift[0].component == "api"
    assert "1.0.0" in drift[0].message
    assert "2.0.0" in drift[0].message


def test_state_unknown_component_yields_warning(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    # state references "ghost" but the config no longer declares it
    _write_state(
        tmp_path / ".multicz" / "state.json",
        '{"version": 1, "components": {"ghost": {"version": "1.0.0"}}}\n',
    )
    (tmp_path / "multicz.toml").write_text("""
[project]
state_file = ".multicz/state.json"

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    findings = list(StateDriftCheck().run(_ctx(tmp_path)))
    unknown = [f for f in findings if f.check == "state_unknown_component"]
    assert unknown
    assert unknown[0].level == "warning"
    assert unknown[0].component == "ghost"
