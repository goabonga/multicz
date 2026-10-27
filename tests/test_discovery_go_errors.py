# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover Go discovery error handling and optional root paths."""

from pathlib import Path

from multicz.discovery.context import DiscoveryContext
from multicz.discovery.go import GoDiscovery, _read_go_module


def test_read_go_module_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "go.mod"
    path.write_bytes(b"\xff\xfe\x00")
    assert _read_go_module(path) is None


def test_read_go_module_skips_lines_before_module(tmp_path: Path) -> None:
    path = tmp_path / "go.mod"
    path.write_text("// header\ngo 1.21\nmodule example.com/org/tool\n")
    assert _read_go_module(path) == "tool"


def test_read_go_module_without_module_line(tmp_path: Path) -> None:
    path = tmp_path / "go.mod"
    path.write_text("go 1.21\n")
    assert _read_go_module(path) is None


def test_read_go_module_with_empty_path(tmp_path: Path) -> None:
    path = tmp_path / "go.mod"
    path.write_text("module /\n")
    assert _read_go_module(path) is None


def test_module_without_name_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("go 1.21\n")
    assert list(GoDiscovery().discover(tmp_path, DiscoveryContext(repo=tmp_path))) == []


def test_root_paths_include_sum_and_dockerfile(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/tool\n")
    (tmp_path / "go.sum").write_text("")
    (tmp_path / "Dockerfile").write_text("")
    results = list(GoDiscovery().discover(tmp_path, DiscoveryContext(repo=tmp_path)))
    assert results[0].component.paths == ["**/*.go", "go.mod", "go.sum", "Dockerfile"]
