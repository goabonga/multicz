# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover Python discovery handling of malformed pyproject files."""

from pathlib import Path

from multicz.discovery.python import _read_pyproject_info, _read_uv_workspace


def test_read_pyproject_info_unparseable(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text("not [valid toml")
    assert _read_pyproject_info(path) is None


def test_read_uv_workspace_unparseable(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text("not [valid toml")
    assert _read_uv_workspace(path) == ([], [])


def test_read_uv_workspace_without_tool_table(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "x"\n')
    assert _read_uv_workspace(path) == ([], [])


def test_read_uv_workspace_with_scalar_uv_table(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool]\nuv = "nope"\n')
    assert _read_uv_workspace(path) == ([], [])


def test_read_uv_workspace_with_scalar_workspace(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.uv]\nworkspace = "nope"\n')
    assert _read_uv_workspace(path) == ([], [])
