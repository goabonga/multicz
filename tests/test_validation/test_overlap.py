# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for PathOverlapCheck in isolation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from multicz.config import ComponentMatcher, load_config
from multicz.validation._base import ValidationContext
from multicz.validation.overlap import PathOverlapCheck


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "x@y")
    _git(tmp_path, "config", "user.name", "x")
    return tmp_path


def _ctx(repo: Path) -> ValidationContext:
    config = load_config(repo / "multicz.toml")
    return ValidationContext(
        repo=repo, config=config, matcher=ComponentMatcher(config.components)
    )


def _setup_overlap(repo: Path, policy: str | None) -> None:
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("x = 1\n")
    project_block = (
        f'\n[project]\noverlap_policy = "{policy}"\n' if policy else ""
    )
    (repo / "multicz.toml").write_text(project_block + """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[components.lib]
paths = ["src/**"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")


def test_overlap_error_policy_yields_error(repo: Path):
    _setup_overlap(repo, policy="error")
    findings = list(PathOverlapCheck().run(_ctx(repo)))
    assert findings
    assert findings[0].level == "error"
    assert findings[0].check == "path_overlap"


def test_overlap_first_match_yields_warning(repo: Path):
    _setup_overlap(repo, policy="first-match")
    findings = list(PathOverlapCheck().run(_ctx(repo)))
    assert findings
    assert findings[0].level == "warning"


def test_overlap_all_yields_info(repo: Path):
    _setup_overlap(repo, policy="all")
    findings = list(PathOverlapCheck().run(_ctx(repo)))
    assert findings
    assert findings[0].level == "info"


def test_overlap_allow_yields_nothing(repo: Path):
    _setup_overlap(repo, policy="allow")
    findings = list(PathOverlapCheck().run(_ctx(repo)))
    assert findings == []
