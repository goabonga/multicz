from datetime import date
from pathlib import Path

from multicz.changelog import insert_section, render_body, render_section, update_changelog_file
from multicz.commits import parse_commit
from multicz.config import ChangelogSection


def test_render_default_groups_feat_fix_perf_revert():
    commits = [
        parse_commit("aaaaaaa", "feat(api): add login", ()),
        parse_commit("bbbbbbb", "fix: null token", ()),
        parse_commit("ccccccc", "perf: tighter loop", ()),
        parse_commit("ddddddd", "chore: tweak", ()),
        parse_commit("eeeeeee", "feat!: rewrite", ()),
        parse_commit("fffffff", "revert: drop x feature", ()),
    ]
    text = render_section("1.3.0", commits, today=date(2026, 4, 30))

    assert text.startswith("## [1.3.0] - 2026-04-30\n")
    assert "### Breaking changes" in text
    assert "### Features" in text
    assert "### Fixes" in text
    assert "### Performance" in text
    assert "### Reverts" in text
    # chore is silently dropped by default
    assert "chore" not in text
    assert "tweak" not in text
    # ordering: Breaking < Features < Fixes < Performance < Reverts
    order = ["Breaking changes", "Features", "Fixes", "Performance", "Reverts"]
    indices = [text.index(f"### {s}") for s in order]
    assert indices == sorted(indices)
    assert "**api**: add login" in text
    assert "drop x feature" in text


def test_render_keepachangelog_vocabulary():
    sections = [
        ChangelogSection(title="Added", types=["feat"]),
        ChangelogSection(title="Fixed", types=["fix"]),
        ChangelogSection(title="Changed", types=["refactor"]),
    ]
    commits = [
        parse_commit("a", "feat: x", ()),
        parse_commit("b", "fix: y", ()),
        parse_commit("c", "refactor: z", ()),
        parse_commit("d", "perf: w", ()),  # not claimed -> dropped
    ]
    body = render_body(commits, sections=sections, breaking_title="")
    assert "### Added" in body
    assert "### Fixed" in body
    assert "### Changed" in body
    assert "Performance" not in body
    assert "perf" not in body


def test_render_other_section_keeps_unmatched():
    sections = [ChangelogSection(title="Features", types=["feat"])]
    commits = [
        parse_commit("a", "feat: x", ()),
        parse_commit("b", "docs: y", ()),
        parse_commit("c", "test: z", ()),
    ]
    body = render_body(commits, sections=sections, other_title="Misc")
    assert "### Features" in body
    assert "### Misc" in body
    # Misc bucket holds the unclaimed types
    misc_index = body.index("### Misc")
    assert "y" in body[misc_index:]
    assert "z" in body[misc_index:]


def test_render_breaking_disabled_falls_through():
    sections = [ChangelogSection(title="Features", types=["feat"])]
    commits = [parse_commit("a", "feat!: rewrite", ())]
    body = render_body(commits, sections=sections, breaking_title="")
    # no Breaking changes header — the breaking commit lands in Features
    assert "### Breaking" not in body
    assert "### Features" in body
    assert "rewrite" in body


def test_render_only_chore_means_no_notable_changes():
    commits = [parse_commit("a", "chore: x", ()), parse_commit("b", "docs: y", ())]
    body = render_body(commits)
    assert "_No notable changes._" in body


def test_render_no_commits():
    text = render_section("1.0.0", [], today=date(2026, 4, 30))
    assert "_No notable changes._" in text


def test_insert_into_empty_file_adds_preamble():
    section = render_section(
        "1.0.0",
        [parse_commit("a", "feat: x", ())],
        today=date(2026, 4, 30),
    )
    out = insert_section("", section)
    assert out.startswith("# Changelog")
    assert "## [1.0.0]" in out


def test_insert_before_existing_release():
    section = render_section(
        "2.0.0",
        [parse_commit("a", "feat: y", ())],
        today=date(2026, 4, 30),
    )
    existing = (
        "# Changelog\n\n"
        "All notable changes...\n\n"
        "## [1.0.0] - 2026-01-01\n\n"
        "### Features\n\n- old (`zzz`)\n"
    )
    out = insert_section(existing, section)
    assert out.index("## [2.0.0]") < out.index("## [1.0.0]")
    assert "old (`zzz`)" in out


def test_update_changelog_file_creates_file(tmp_path: Path):
    target = tmp_path / "nested" / "CHANGELOG.md"
    update_changelog_file(
        target,
        "1.0.0",
        [parse_commit("a1b2c3d", "feat: x", ())],
        today=date(2026, 4, 30),
    )
    assert target.exists()
    content = target.read_text()
    assert content.startswith("# Changelog")
    assert "## [1.0.0] - 2026-04-30" in content
    assert "(`a1b2c3d`)" in content


def test_update_changelog_file_prepends_to_existing(tmp_path: Path):
    target = tmp_path / "CHANGELOG.md"
    target.write_text(
        "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n### Features\n\n- old (`zzz`)\n"
    )
    update_changelog_file(
        target,
        "1.1.0",
        [parse_commit("a", "fix: y", ())],
        today=date(2026, 4, 30),
    )
    content = target.read_text()
    assert content.index("## [1.1.0]") < content.index("## [1.0.0]")
