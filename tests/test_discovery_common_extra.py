# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover manifest lookup ignoring directories named like a manifest."""

from pathlib import Path

from multicz.discovery._common import _find_manifests


def test_find_manifests_ignores_directories(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").mkdir()
    real = tmp_path / "crate" / "Cargo.toml"
    real.parent.mkdir()
    real.write_text("")
    assert _find_manifests(tmp_path, "Cargo.toml") == [real]
