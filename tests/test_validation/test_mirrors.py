# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for MirrorTargetsCheck in isolation."""

from __future__ import annotations

from pathlib import Path

from multicz.config import ComponentMatcher, load_config
from multicz.validation._base import ValidationContext
from multicz.validation.mirrors import MirrorTargetsCheck


def _ctx(repo: Path) -> ValidationContext:
    config = load_config(repo / "multicz.toml")
    return ValidationContext(
        repo=repo, config=config, matcher=ComponentMatcher(config.components)
    )


def test_mirror_to_unowned_file_is_info(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    (tmp_path / "values.yaml").write_text("foo: bar\n")
    (tmp_path / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "values.yaml", key = "version" }]
""")
    findings = list(MirrorTargetsCheck().run(_ctx(tmp_path)))
    assert any(
        f.check == "mirror_target_unowned" and f.level == "info"
        for f in findings
    )


def test_mirror_self_target_is_warning(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    (tmp_path / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "pyproject.toml", key = "project.version" }]
""")
    findings = list(MirrorTargetsCheck().run(_ctx(tmp_path)))
    selfish = [f for f in findings if f.check == "mirror_self_target"]
    assert selfish
    assert selfish[0].level == "warning"
    assert selfish[0].component == "api"
