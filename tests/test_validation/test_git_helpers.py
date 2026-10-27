# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

from multicz.validation._git import _list_tracked_files


def test_list_tracked_files_outside_repo_is_empty(tmp_path: Path):
    assert _list_tracked_files(tmp_path) == []


def test_list_tracked_files_missing_directory_is_empty(tmp_path: Path):
    assert _list_tracked_files(tmp_path / "nope") == []
