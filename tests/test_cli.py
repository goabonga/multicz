"""End-to-end CLI tests using typer's CliRunner."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app

CONFIG = """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]
changelog = "CHANGELOG.md"

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
changelog = "charts/myapp/CHANGELOG.md"
"""

INITIAL = {
    "multicz.toml": CONFIG,
    "pyproject.toml": '[project]\nname = "x"\nversion = "1.2.0"\n',
    "src/main.py": "x = 1\n",
    "charts/myapp/Chart.yaml": (
        "apiVersion: v2\nname: x\nversion: 0.4.0\nappVersion: 1.2.0\n"
    ),
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout


def _write(repo: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def _commit(repo: Path, files: dict[str, str], message: str) -> None:
    _write(repo, files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit(tmp_path, INITIAL, "chore: init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_status_no_bumps(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "no bumps pending" in result.stdout


def test_bump_dry_run_does_not_modify_files(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add stuff")
    before = (repo / "pyproject.toml").read_text()
    result = runner.invoke(app, ["bump", "--dry-run"])
    assert result.exit_code == 0
    assert (repo / "pyproject.toml").read_text() == before
    assert "would bump" in result.stdout


def test_bump_writes_files(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add stuff")
    result = runner.invoke(app, ["bump"])
    assert result.exit_code == 0, result.stdout
    assert 'version = "1.3.0"' in (repo / "pyproject.toml").read_text()
    chart = (repo / "charts/myapp/Chart.yaml").read_text()
    assert "version: 0.4.1" in chart
    assert "appVersion: 1.3.0" in chart


def test_bump_commit_and_tag(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add stuff")
    result = runner.invoke(app, ["bump", "--commit", "--tag"])
    assert result.exit_code == 0, result.stdout

    head_msg = _git(repo, "log", "-1", "--format=%B").strip()
    assert head_msg.startswith("chore(release): bump")
    assert "api 1.2.0 -> 1.3.0" in head_msg
    assert "chart 0.4.0 -> 0.4.1" in head_msg

    tags = _git(repo, "tag").split()
    assert "api-v1.3.0" in tags
    assert "chart-v0.4.1" in tags


def test_bump_release_commit_is_skipped_on_next_run(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add stuff")
    runner.invoke(app, ["bump", "--commit", "--tag"])
    # second run should be a no-op since the only new commit is chore(release)
    result = runner.invoke(app, ["bump", "--dry-run"])
    assert "no bumps pending" in result.stdout


def test_bump_json_output(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add stuff")
    result = runner.invoke(app, ["bump", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["bumps"]["api"]["next"] == "1.3.0"
    assert payload["bumps"]["chart"]["next"] == "0.4.1"


def test_get_returns_current_version(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["get", "api"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "1.2.0"


def test_changelog_markdown_groups_by_section(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix(api): null token")
    _commit(repo, {"src/main.py": "x = 4\n"}, "feat!: rewrite client")

    result = runner.invoke(app, ["changelog", "--output", "md", "--component", "api"])
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    assert "## api" in out
    assert "### Breaking changes" in out
    assert "### Features" in out
    assert "### Fixes" in out
    # breaking comes first per _MD_SECTIONS order
    assert out.index("Breaking changes") < out.index("Features")
    assert out.index("Features") < out.index("Fixes")


def test_changelog_markdown_no_changes(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["changelog", "--output", "md", "--component", "api"])
    assert result.exit_code == 0
    assert "_No notable changes._" in result.stdout


def test_changelog_markdown_uses_project_sections(repo: Path, runner: CliRunner):
    # rewrite multicz.toml with custom sections (keep-a-changelog vocabulary)
    (repo / "multicz.toml").write_text(CONFIG + """
[[project.changelog_sections]]
title = "Added"
types = ["feat"]

[[project.changelog_sections]]
title = "Fixed"
types = ["fix"]
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): login")
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: null token")
    _commit(repo, {"src/main.py": "x = 4\n"}, "perf: tighter loop")

    result = runner.invoke(app, ["changelog", "--output", "md", "--component", "api"])
    assert result.exit_code == 0, result.stdout
    assert "### Added" in result.stdout
    assert "### Fixed" in result.stdout
    # Performance is no longer a configured section -> commit dropped
    assert "Performance" not in result.stdout
    assert "tighter loop" not in result.stdout


def test_bump_writes_changelog_with_custom_sections(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + """
[[project.changelog_sections]]
title = "Added"
types = ["feat"]
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): login")
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: y")  # not in any section -> dropped

    result = runner.invoke(app, ["bump"])
    assert result.exit_code == 0, result.stdout
    api_log = (repo / "CHANGELOG.md").read_text()
    assert "### Added" in api_log
    assert "Fixes" not in api_log
    assert "Fixed" not in api_log


def test_bump_writes_changelogs(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): login")
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: null token")

    result = runner.invoke(app, ["bump"])
    assert result.exit_code == 0, result.stdout

    api_log = (repo / "CHANGELOG.md").read_text()
    assert "## [1.3.0]" in api_log
    assert "### Features" in api_log
    assert "**api**: login" in api_log

    chart_log = (repo / "charts/myapp/CHANGELOG.md").read_text()
    assert "## [0.4.1]" in chart_log
    # cascade-only bump => no commits to enumerate, but the section still exists
    assert "_No notable changes._" in chart_log or "### " in chart_log


def test_bump_no_changelog_flag(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): login")
    result = runner.invoke(app, ["bump", "--no-changelog"])
    assert result.exit_code == 0
    assert not (repo / "CHANGELOG.md").exists()


def test_bump_commit_includes_changelog(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): login")
    runner.invoke(app, ["bump", "--commit", "--tag"])

    files = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert "CHANGELOG.md" in files
    assert "charts/myapp/CHANGELOG.md" in files


def test_validate_clean_repo_exits_zero(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0
    assert "no issues found" in result.output


def test_validate_missing_bump_file_exits_one(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + "\n")
    # delete the file the api bump_file points at
    (repo / "pyproject.toml").unlink()
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "bump_file" in result.output
    assert "does not exist" in result.output


def test_validate_strict_exits_two_on_warnings(repo: Path, runner: CliRunner):
    # Overlap between api and lib on src/** with policy = first-match -> warning
    (repo / "multicz.toml").write_text("""
[project]
overlap_policy = "first-match"
""" + CONFIG + """
[components.lib]
paths = ["src/**"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    result = runner.invoke(app, ["validate", "--strict"])
    assert result.exit_code == 2
    assert "path_overlap" in result.output


def test_validate_default_overlap_policy_errors(repo: Path, runner: CliRunner):
    # No explicit policy -> default "error" -> overlap is an error -> exit 1
    (repo / "multicz.toml").write_text(CONFIG + """
[components.lib]
paths = ["src/**"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "path_overlap" in result.output


def test_overlap_policy_all_bumps_every_component(repo: Path, runner: CliRunner):
    """A shared file under overlap_policy = 'all' bumps every claiming component."""
    (repo / "multicz.toml").write_text("""
[project]
overlap_policy = "all"

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[components.lib]
paths = ["src/**"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: shared change")
    result = runner.invoke(app, ["plan", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "api" in payload["bumps"]
    assert "lib" in payload["bumps"]


def test_validate_json_output(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["validate", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "findings" in payload
    assert "summary" in payload
    assert payload["summary"]["errors"] == 0


def test_validate_check_accepts_conventional(tmp_path: Path, runner: CliRunner):
    """rename of test_check_accepts_conventional kept here for clarity."""
    msg = tmp_path / "msg"
    msg.write_text("feat: x\n")
    result = runner.invoke(app, ["check", str(msg)])
    assert result.exit_code == 0


def test_check_accepts_conventional(tmp_path: Path, runner: CliRunner):
    msg = tmp_path / "msg"
    msg.write_text("feat(api): add login\n")
    result = runner.invoke(app, ["check", str(msg)])
    assert result.exit_code == 0


def test_check_rejects_non_conventional(tmp_path: Path, runner: CliRunner):
    msg = tmp_path / "msg"
    msg.write_text("oopsie no convention here\n")
    result = runner.invoke(app, ["check", str(msg)])
    assert result.exit_code == 1
    # error printed to stderr (mixed with stdout in CliRunner default)
    assert "invalid commit message" in result.output or "invalid" in result.output


def test_check_rejects_unknown_type_when_restricted(tmp_path: Path, runner: CliRunner):
    msg = tmp_path / "msg"
    msg.write_text("chore: tweak\n")
    result = runner.invoke(app, ["check", str(msg), "--type", "feat", "--type", "fix"])
    assert result.exit_code == 1


def test_check_missing_file(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["check", "/no/such/file"])
    assert result.exit_code == 1


def test_plan_text_lists_reasons_per_component(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 0, result.stdout

    assert "api: 1.2.0 → 1.3.0 (minor)" in result.stdout
    assert "feat(api): add login" in result.stdout
    # Mirror cascade reason for chart
    assert "chart: 0.4.0 → 0.4.1 (patch)" in result.stdout
    assert "mirror cascade from api" in result.stdout


def test_plan_json_emits_structured_reasons(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    result = runner.invoke(app, ["plan", "--output", "json"])
    assert result.exit_code == 0, result.stdout

    payload = json.loads(result.stdout)
    api = payload["bumps"]["api"]
    assert api["current"] == "1.2.0"
    assert api["next"] == "1.3.0"
    assert api["kind"] == "minor"
    [reason] = api["reasons"]
    assert reason["kind"] == "commit"
    assert reason["type"] == "feat"
    assert reason["scope"] == "api"
    assert reason["breaking"] is False
    assert "src/main.py" in reason["files"]

    chart = payload["bumps"]["chart"]
    [mirror_reason] = chart["reasons"]
    assert mirror_reason["kind"] == "mirror"
    assert mirror_reason["upstream"] == "api"
    assert mirror_reason["key"] == "appVersion"


def test_plan_no_bumps(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 0
    assert "no bumps pending" in result.stdout


def test_plan_pre_and_finalize_mutually_exclusive(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["plan", "--pre", "rc", "--finalize"])
    assert result.exit_code == 1


def test_release_notes_for_upcoming_bump(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: null token")
    result = runner.invoke(app, ["release-notes", "api"])
    assert result.exit_code == 0, result.stdout
    assert "### Features" in result.stdout
    assert "**api**: add login" in result.stdout
    assert "### Fixes" in result.stdout


def test_release_notes_all_renders_every_bumping_component(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    result = runner.invoke(app, ["release-notes", "--all"])
    assert result.exit_code == 0, result.stdout
    assert "## api" in result.stdout
    assert "## chart" in result.stdout
    # mirror cascade: chart has no commits but its own (the rc body)
    # api section has the feat
    assert "add login" in result.stdout


def test_release_notes_text_output(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    result = runner.invoke(app, ["release-notes", "api", "--output", "text"])
    assert result.exit_code == 0
    assert "api 1.2.0 → 1.3.0" in result.output
    assert "feat: add login" in result.output


def test_release_notes_json_output(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    result = runner.invoke(app, ["release-notes", "api", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    [section] = payload["sections"]
    assert section["component"] == "api"
    assert section["from_version"] == "1.2.0"
    assert section["to_version"] == "1.3.0"
    [commit] = section["commits"]
    assert commit["type"] == "feat"


def test_release_notes_for_past_tag_uses_previous_stable(repo: Path, runner: CliRunner):
    """When asking for notes on a stable tag, multicz looks at commits
    since the previous *stable* tag — not since the most recent rc."""
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: bug")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    runner.invoke(app, ["bump", "--finalize", "--commit", "--tag"])

    result = runner.invoke(app, ["release-notes", "--tag", "api-v1.3.0"])
    assert result.exit_code == 0, result.stdout
    # both commits land in the consolidated notes
    assert "add login" in result.stdout
    assert "bug" in result.stdout


def test_release_notes_for_rc_tag_uses_previous_tag(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: bug")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])

    result = runner.invoke(
        app, ["release-notes", "--tag", "api-v1.3.0-rc.2"]
    )
    assert result.exit_code == 0
    # rc.2's notes only show delta since rc.1
    assert "bug" in result.stdout
    assert "add login" not in result.stdout


def test_release_notes_unknown_tag_errors(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["release-notes", "--tag", "unrelated-tag"])
    assert result.exit_code == 1
    assert "doesn't match any component" in result.output


def test_release_notes_arg_required(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["release-notes"])
    assert result.exit_code == 1


def test_release_notes_tag_exclusive_with_component(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["release-notes", "api", "--tag", "api-v1.0.0"])
    assert result.exit_code == 1


def test_explain_lists_files_per_commit(repo: Path, runner: CliRunner):
    _commit(repo, {
        "src/main.py": "x = 2\n",
        "src/auth.py": "x = 1\n",
    }, "feat(api): add login flow")

    result = runner.invoke(app, ["explain", "api"])
    assert result.exit_code == 0, result.stdout
    assert "Component: api" in result.stdout
    assert "Current version: 1.2.0" in result.stdout
    assert "Next version:    1.3.0" in result.stdout
    assert "feat(api): add login flow" in result.stdout
    assert "src/main.py" in result.stdout
    assert "src/auth.py" in result.stdout


def test_explain_for_mirror_cascade(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add stuff")
    result = runner.invoke(app, ["explain", "chart"])
    assert result.exit_code == 0
    assert "mirror cascade from api" in result.stdout
    assert "charts/myapp/Chart.yaml" in result.stdout


def test_explain_unknown_component(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["explain", "nonexistent"])
    assert result.exit_code == 1
    assert "unknown component" in result.output


def test_explain_idle_component(repo: Path, runner: CliRunner):
    # No commits since init -> nothing to explain
    result = runner.invoke(app, ["explain", "api"])
    assert result.exit_code == 0
    assert "no bump pending" in result.stdout


def test_bump_pre_rc_enters_cycle(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    result = runner.invoke(app, ["bump", "--pre", "rc"])
    assert result.exit_code == 0, result.stdout
    assert 'version = "1.3.0-rc.1"' in (repo / "pyproject.toml").read_text()


def test_bump_pre_rc_increments_counter(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: bug")
    result = runner.invoke(app, ["bump", "--pre", "rc"])
    assert result.exit_code == 0, result.stdout
    assert 'version = "1.3.0-rc.2"' in (repo / "pyproject.toml").read_text()


def test_bump_finalize_drops_suffix(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    # No new commits -> --finalize still works
    result = runner.invoke(app, ["bump", "--finalize"])
    assert result.exit_code == 0, result.stdout
    assert 'version = "1.3.0"' in (repo / "pyproject.toml").read_text()


def test_bump_no_flags_after_rc_auto_finalizes(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: bug")
    result = runner.invoke(app, ["bump"])  # no --pre, no --finalize
    assert result.exit_code == 0, result.stdout
    # Auto-finalize: drop the suffix even though there were new commits
    assert 'version = "1.3.0"' in (repo / "pyproject.toml").read_text()


def test_bump_pre_and_finalize_mutually_exclusive(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    result = runner.invoke(app, ["bump", "--pre", "rc", "--finalize"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output.lower()


def test_finalize_consolidate_lists_all_commits_since_last_stable(repo: Path, runner: CliRunner):
    # default strategy = consolidate
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: handle null")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    runner.invoke(app, ["bump", "--finalize"])

    text = (repo / "CHANGELOG.md").read_text()
    final_section = text.split("## [1.3.0-rc.2]")[0]
    assert "## [1.3.0]" in final_section
    # both commits accumulated since the last stable tag (none -> all)
    assert "add login" in final_section
    assert "handle null" in final_section
    # RC sections still present below
    assert "## [1.3.0-rc.1]" in text
    assert "## [1.3.0-rc.2]" in text


def test_finalize_promote_drops_intermediate_rcs(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + '\n[project]\nfinalize_strategy = "promote"\n')
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: handle null")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    runner.invoke(app, ["bump", "--finalize"])

    text = (repo / "CHANGELOG.md").read_text()
    assert "## [1.3.0]" in text
    assert "## [1.3.0-rc.1]" not in text
    assert "## [1.3.0-rc.2]" not in text
    assert "add login" in text
    assert "handle null" in text


def test_finalize_annotate_uses_only_commits_since_last_rc(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + '\n[project]\nfinalize_strategy = "annotate"\n')
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: handle null")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    # No commits between rc.2 and finalize -> annotate keeps the empty section
    runner.invoke(app, ["bump", "--finalize"])

    text = (repo / "CHANGELOG.md").read_text()
    final_section = text.split("## [1.3.0-rc.2]")[0]
    assert "## [1.3.0]" in final_section
    assert "_No notable changes._" in final_section
    # RC sections still present
    assert "## [1.3.0-rc.1]" in text
    assert "## [1.3.0-rc.2]" in text


def test_bump_pre_creates_tag_with_rc_suffix(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    tags = _git(repo, "tag").split()
    assert "api-v1.3.0-rc.1" in tags


def test_bump_debian_format_prepends_stanza(tmp_path: Path, runner: CliRunner):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "deb@test.com")
    _git(tmp_path, "config", "user.name", "Deb Maintainer")

    files = {
        "multicz.toml": """
[components.mypkg]
paths = ["debian/**", "src/**"]
format = "debian"

[components.mypkg.debian]
changelog = "debian/changelog"
distribution = "unstable"
urgency = "medium"
""",
        "debian/changelog": (
            "mypkg (1.2.0-1) unstable; urgency=medium\n"
            "\n"
            "  * Initial release.\n"
            "\n"
            " -- Deb Maintainer <deb@test.com>  Sun, 01 Jan 2023 00:00:00 +0000\n"
        ),
        "src/main.py": "x = 1\n",
    }
    _commit(tmp_path, files, "chore: init")

    monkey = pytest.MonkeyPatch()
    monkey.chdir(tmp_path)
    try:
        _commit(tmp_path, {"src/main.py": "x = 2\n"}, "feat: add login")
        result = runner.invoke(app, ["bump"])
        assert result.exit_code == 0, result.stdout

        text = (tmp_path / "debian/changelog").read_text()
        assert text.index("mypkg (1.3.0-1)") < text.index("mypkg (1.2.0-1)")
        assert "mypkg (1.3.0-1) unstable; urgency=medium" in text
        assert "  * feat: Add login" in text
        assert "Deb Maintainer <deb@test.com>" in text
    finally:
        monkey.undo()


def test_bump_debian_dry_run_does_not_modify(tmp_path: Path, runner: CliRunner):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "deb@test.com")
    _git(tmp_path, "config", "user.name", "Deb")

    files = {
        "multicz.toml": """
[components.mypkg]
paths = ["debian/**", "src/**"]
format = "debian"
""",
        "debian/changelog": (
            "mypkg (1.0.0-1) unstable; urgency=medium\n"
            "\n  * Initial.\n\n"
            " -- x <x@y>  Sun, 01 Jan 2023 00:00:00 +0000\n"
        ),
        "src/main.py": "x = 1\n",
    }
    _commit(tmp_path, files, "chore: init")

    monkey = pytest.MonkeyPatch()
    monkey.chdir(tmp_path)
    try:
        _commit(tmp_path, {"src/main.py": "x = 2\n"}, "feat: x")
        before = (tmp_path / "debian/changelog").read_text()
        result = runner.invoke(app, ["bump", "--dry-run"])
        assert result.exit_code == 0
        assert (tmp_path / "debian/changelog").read_text() == before
        assert "1.1.0" in result.stdout
    finally:
        monkey.undo()


def test_bump_debian_with_revision_3(tmp_path: Path, runner: CliRunner):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "deb@test.com")
    _git(tmp_path, "config", "user.name", "Deb")

    files = {
        "multicz.toml": """
[components.mypkg]
paths = ["debian/**", "src/**"]
format = "debian"

[components.mypkg.debian]
debian_revision = 3
""",
        "debian/changelog": (
            "mypkg (1.0.0-3) unstable; urgency=medium\n"
            "\n  * Old.\n\n"
            " -- x <x@y>  Sun, 01 Jan 2023 00:00:00 +0000\n"
        ),
        "src/main.py": "x = 1\n",
    }
    _commit(tmp_path, files, "chore: init")

    monkey = pytest.MonkeyPatch()
    monkey.chdir(tmp_path)
    try:
        _commit(tmp_path, {"src/main.py": "x = 2\n"}, "feat: x")
        result = runner.invoke(app, ["bump"])
        assert result.exit_code == 0, result.stdout
        text = (tmp_path / "debian/changelog").read_text()
        assert "mypkg (1.1.0-3)" in text
    finally:
        monkey.undo()


def test_init_auto_detects_pyproject(tmp_path: Path, runner: CliRunner):
    target = tmp_path / "fresh"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "auto-app"\nversion = "0.1.0"\n'
    )
    (target / "src").mkdir()
    os.chdir(target)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.stdout
    text = (target / "multicz.toml").read_text()
    assert "[components.auto-app]" in text
    assert "Dockerfile" not in text
    assert ".dockerignore" not in text


def test_init_bare_writes_generic_stub(tmp_path: Path, runner: CliRunner):
    target = tmp_path / "fresh"
    target.mkdir()
    os.chdir(target)
    result = runner.invoke(app, ["init", "--bare"])
    assert result.exit_code == 0
    text = (target / "multicz.toml").read_text()
    assert "[components.app]" in text


def test_init_fails_when_no_manifests(tmp_path: Path, runner: CliRunner):
    target = tmp_path / "empty"
    target.mkdir()
    os.chdir(target)
    result = runner.invoke(app, ["init"])
    assert result.exit_code != 0
    assert not (target / "multicz.toml").exists()


def test_init_force_overwrites(tmp_path: Path, runner: CliRunner):
    target = tmp_path / "fresh"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "auto-app"\nversion = "0.1.0"\n'
    )
    (target / "multicz.toml").write_text("# old\n")
    os.chdir(target)
    result = runner.invoke(app, ["init"])
    assert result.exit_code != 0  # no --force

    result = runner.invoke(app, ["init", "--force"])
    assert result.exit_code == 0
    assert "[components.auto-app]" in (target / "multicz.toml").read_text()
