# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Edge cases of StateDriftCheck: nothing to compare, nothing readable."""

from __future__ import annotations

from pathlib import Path

from multicz.config import ComponentMatcher, load_config
from multicz.validation._base import ValidationContext
from multicz.validation.state import StateDriftCheck


def _ctx(repo: Path) -> ValidationContext:
    config = load_config(repo / "multicz.toml")
    return ValidationContext(repo=repo, config=config, matcher=ComponentMatcher(config.components))


def _write_state(repo: Path, body: str) -> None:
    path = repo / ".multicz" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_missing_state_file_yields_nothing(tmp_path: Path):
    (tmp_path / "multicz.toml").write_text("""
[project]
state_file = ".multicz/state.json"

[components.api]
paths = ["src/**"]
""")
    assert list(StateDriftCheck().run(_ctx(tmp_path))) == []


def test_component_without_bump_files_is_skipped(tmp_path: Path):
    _write_state(tmp_path, '{"version": 1, "components": {"api": {"version": "1.0.0"}}}')
    (tmp_path / "multicz.toml").write_text("""
[project]
state_file = ".multicz/state.json"

[components.api]
paths = ["src/**"]
""")
    assert list(StateDriftCheck().run(_ctx(tmp_path))) == []


def test_unreadable_bump_file_is_skipped(tmp_path: Path):
    _write_state(tmp_path, '{"version": 1, "components": {"api": {"version": "1.0.0"}}}')
    (tmp_path / "multicz.toml").write_text("""
[project]
state_file = ".multicz/state.json"

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    assert list(StateDriftCheck().run(_ctx(tmp_path))) == []
