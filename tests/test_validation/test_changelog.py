# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for ChangelogPathCheck and DebianChangelogCheck in isolation."""

from __future__ import annotations

from pathlib import Path

from multicz.config import ComponentMatcher, load_config
from multicz.validation._base import ValidationContext
from multicz.validation.changelog import (
    ChangelogPathCheck,
    DebianChangelogCheck,
)


def _ctx(repo: Path) -> ValidationContext:
    config = load_config(repo / "multicz.toml")
    return ValidationContext(
        repo=repo, config=config, matcher=ComponentMatcher(config.components)
    )


def test_changelog_directory_is_error(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    (tmp_path / "CHANGELOG.md").mkdir()  # dir, not a file
    (tmp_path / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
changelog = "CHANGELOG.md"
""")
    findings = list(ChangelogPathCheck().run(_ctx(tmp_path)))
    assert findings
    assert findings[0].level == "error"
    assert findings[0].check == "changelog_not_a_file"


def test_debian_changelog_unparseable_is_error(tmp_path: Path):
    debian = tmp_path / "debian"
    debian.mkdir()
    (debian / "changelog").write_text("not a debian changelog\n")
    (tmp_path / "multicz.toml").write_text("""
[components.mypkg]
paths = ["debian/**"]
format = "debian"
""")
    findings = list(DebianChangelogCheck().run(_ctx(tmp_path)))
    bad = [f for f in findings if f.check == "debian_changelog_unparseable"]
    assert bad
    assert bad[0].level == "error"
