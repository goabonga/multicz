# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

from multicz.state import load_state


def test_load_state_missing_file_returns_none(tmp_path: Path):
    assert load_state(tmp_path / "state.json") is None


def test_load_state_invalid_json_returns_none(tmp_path: Path):
    f = tmp_path / "state.json"
    f.write_text("{not json")
    assert load_state(f) is None


def test_load_state_non_object_returns_none(tmp_path: Path):
    f = tmp_path / "state.json"
    f.write_text("[1, 2, 3]")
    assert load_state(f) is None
