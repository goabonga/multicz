# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for BumpFilesExistCheck in isolation."""

from __future__ import annotations

from pathlib import Path

from multicz.config import ComponentMatcher, load_config
from multicz.validation._base import ValidationContext
from multicz.validation.bump_files import BumpFilesExistCheck


def _ctx(repo: Path) -> ValidationContext:
    config = load_config(repo / "multicz.toml")
    return ValidationContext(
        repo=repo, config=config, matcher=ComponentMatcher(config.components)
    )


def test_existing_bump_file_yields_nothing(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    (tmp_path / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    findings = list(BumpFilesExistCheck().run(_ctx(tmp_path)))
    assert findings == []


def test_missing_bump_file_yields_error(tmp_path: Path):
    (tmp_path / "multicz.toml").write_text("""
[components.api]
paths = ["src/**"]
bump_files = [{ file = "missing.toml", key = "version" }]
""")
    findings = list(BumpFilesExistCheck().run(_ctx(tmp_path)))
    assert len(findings) == 1
    f = findings[0]
    assert f.level == "error"
    assert f.check == "bump_files_exist"
    assert f.component == "api"
    assert "missing.toml" in f.message


def test_multiple_bump_files_each_checked(tmp_path: Path):
    (tmp_path / "a.toml").write_text("v = '1.0'\n")
    # b.toml deliberately missing
    (tmp_path / "multicz.toml").write_text("""
[components.api]
paths = ["**"]
bump_files = [
  { file = "a.toml", key = "v" },
  { file = "b.toml", key = "v" },
]
""")
    findings = list(BumpFilesExistCheck().run(_ctx(tmp_path)))
    assert len(findings) == 1
    assert "b.toml" in findings[0].message
