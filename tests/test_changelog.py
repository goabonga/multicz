from datetime import date
from pathlib import Path

from multicz.changelog import insert_section, render_section, update_changelog_file
from multicz.commits import parse_commit


def _commit(sha: str, msg: str, scope: str | None = None) -> object:
    return parse_commit(sha, msg, ())


def test_render_groups_by_section():
    commits = [
        parse_commit("aaaaaaa", "feat(api): add login", ()),
        parse_commit("bbbbbbb", "fix: null token", ()),
        parse_commit("ccccccc", "feat!: rewrite", ()),
        parse_commit("ddddddd", "chore: tweak", ()),
    ]
    text = render_section("1.3.0", commits, today=date(2026, 4, 30))

    assert text.startswith("## [1.3.0] - 2026-04-30\n")
    assert "### Breaking changes" in text
    assert "### Features" in text
    assert "### Fixes" in text
    assert "### Other" in text
    # ordering: Breaking < Features < Fixes < Other
    order = ["Breaking changes", "Features", "Fixes", "Other"]
    indices = [text.index(f"### {s}") for s in order]
    assert indices == sorted(indices)
    # scope rendered as bold prefix
    assert "**api**: add login" in text


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
