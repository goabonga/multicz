# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from datetime import date
from pathlib import Path

from multicz.changelog.root import (
    ComponentBumpDigest,
    render_root_section,
    update_root_changelog_file,
)
from multicz.commits import parse_commit
from multicz.config import ChangelogSection

TODAY = date(2026, 4, 30)


def _digests() -> list[ComponentBumpDigest]:
    return [
        ComponentBumpDigest(
            component="web",
            current="1.0.0",
            next_version="1.0.1",
            kind="patch",
            cascade_from="api 0.2.3",
            commits=(
                parse_commit("bbbbbbb", "fix: cap input", ()),
                parse_commit("ccccccc", "chore: tidy", ()),
            ),
        ),
        ComponentBumpDigest(
            component="api",
            current="0.2.2",
            next_version="1.0.0",
            kind="major",
            cascade_from=None,
            commits=(
                parse_commit("aaaaaaa", "feat!: rewrite", ()),
                parse_commit("ddddddd", "feat: pkce", ()),
                parse_commit("", "chore: nosha", ()),
            ),
        ),
    ]


def test_render_root_section_groups_and_prefixes():
    text = render_root_section(_digests(), today=TODAY)
    assert text.startswith("## 2026-04-30\n")
    assert text.index("**api** major") < text.index("**web** patch")
    assert "_(cascade from api 0.2.3)_" in text
    assert "### Breaking changes" in text
    assert "- **api**: rewrite (`aaaaaaa`)" in text
    assert "- **api**: pkce (`ddddddd`)" in text
    assert "- **web**: cap input (`bbbbbbb`)" in text
    assert "tidy" not in text


def test_render_root_section_other_title_matching_a_section():
    sections = [
        ChangelogSection(title="Features", types=["feat"]),
        ChangelogSection(title="Other", types=["chore"]),
    ]
    text = render_root_section(_digests(), today=TODAY, sections=sections, other_title="Other")
    assert "### Other" in text
    assert "- **web**: tidy (`ccccccc`)" in text
    # a commit without sha renders no sha suffix
    assert "- **api**: nosha\n" in text


def test_update_root_changelog_file_creates_then_prepends(tmp_path: Path):
    path = tmp_path / "sub" / "CHANGELOG.md"
    update_root_changelog_file(path, _digests(), today=date(2026, 4, 29))
    first = path.read_text(encoding="utf-8")
    assert first.startswith("# Changelog\n")
    assert "## 2026-04-29" in first

    update_root_changelog_file(path, _digests(), today=TODAY)
    second = path.read_text(encoding="utf-8")
    assert second.startswith("# Changelog\n")
    assert second.index("## 2026-04-30") < second.index("## 2026-04-29")
