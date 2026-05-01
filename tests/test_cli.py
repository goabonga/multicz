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
    assert payload["bumps"]["api"]["next_version"] == "1.3.0"
    assert payload["bumps"]["chart"]["next_version"] == "0.4.1"


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


def test_plan_summary_appends_markdown_table(repo: Path, runner: CliRunner, tmp_path: Path):
    summary = tmp_path / "summary.md"
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")

    result = runner.invoke(app, ["plan", "--summary", str(summary)])
    assert result.exit_code == 0, result.stdout
    text = summary.read_text()
    assert "## Release plan" in text
    assert "| component |" in text
    assert "| `api` |" in text
    assert "| `1.2.0` |" in text
    assert "| `1.3.0` |" in text
    assert "feat(api): add login" in text


def test_plan_summary_empty_plan(repo: Path, runner: CliRunner, tmp_path: Path):
    """With no commits since the last tag, the summary still gets written."""
    summary = tmp_path / "summary.md"
    result = runner.invoke(app, ["plan", "--summary", str(summary)])
    assert result.exit_code == 0
    assert "_No bumps pending._" in summary.read_text()


def test_bump_summary_appends_release_block(repo: Path, runner: CliRunner, tmp_path: Path):
    summary = tmp_path / "summary.md"
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")

    result = runner.invoke(
        app, ["bump", "--commit", "--tag", "--summary", str(summary)]
    )
    assert result.exit_code == 0, result.stdout
    text = summary.read_text()
    assert "## Released" in text
    assert "api-v1.3.0" in text
    assert "Release commit:" in text


def test_summary_appends_when_plan_then_bump(
    repo: Path, runner: CliRunner, tmp_path: Path
):
    """Plan and bump can write to the same summary file in sequence."""
    summary = tmp_path / "summary.md"
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")

    runner.invoke(app, ["plan", "--summary", str(summary)])
    runner.invoke(app, ["bump", "--commit", "--tag", "--summary", str(summary)])

    text = summary.read_text()
    assert "## Release plan" in text
    assert "## Released" in text
    # Order preserved
    assert text.index("## Release plan") < text.index("## Released")


def test_bump_summary_works_with_json_output(
    repo: Path, runner: CliRunner, tmp_path: Path
):
    """--summary and --output json compose: JSON to stdout, markdown to file."""
    summary = tmp_path / "summary.md"
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")

    result = runner.invoke(
        app,
        [
            "bump", "--commit", "--tag",
            "--summary", str(summary),
            "--output", "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["bumps"]["api"]["next_version"] == "1.3.0"
    assert "## Released" in summary.read_text()


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
    assert payload["schema_version"] == 1
    api = payload["bumps"]["api"]
    assert api["current_version"] == "1.2.0"
    assert api["next_version"] == "1.3.0"
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


def test_state_command_without_config(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["state"])
    assert result.exit_code == 1
    assert "no state_file configured" in result.output


def test_state_written_on_bump_and_readable(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
state_file = ".multicz/state.json"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    result = runner.invoke(app, ["bump", "--commit", "--tag"])
    assert result.exit_code == 0, result.stdout

    state_path = repo / ".multicz" / "state.json"
    assert state_path.is_file()

    payload = json.loads(state_path.read_text())
    assert payload["version"] == 1
    assert "git_head" in payload
    assert payload["components"]["api"]["version"] == "1.3.0"
    assert payload["components"]["api"]["tag"] == "api-v1.3.0"

    # The state command renders it
    result = runner.invoke(app, ["state", "--output", "json"])
    assert result.exit_code == 0
    via_cli = json.loads(result.stdout)
    assert via_cli["components"]["api"]["version"] == "1.3.0"


def test_state_drift_detected_by_validate(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
state_file = ".multicz/state.json"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    runner.invoke(app, ["bump", "--commit", "--tag"])

    # Manually edit pyproject.toml after the bump (simulating drift)
    pp = repo / "pyproject.toml"
    pp.write_text(pp.read_text().replace('version = "1.3.0"', 'version = "9.9.9"'))

    result = runner.invoke(app, ["validate", "--strict"])
    assert result.exit_code == 2
    assert "state_drift" in result.output
    assert "1.3.0" in result.output
    assert "9.9.9" in result.output


def test_state_no_drift_when_consistent(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
state_file = ".multicz/state.json"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    runner.invoke(app, ["bump", "--commit", "--tag"])

    result = runner.invoke(app, ["validate", "--strict"])
    assert result.exit_code == 0


def test_unknown_commit_error_policy_clean_cli_message(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
unknown_commit_policy = "error"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "update stuff")
    _commit(repo, {"src/main.py": "x = 3\n"}, "wip")

    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 1
    assert "non-conventional commit" in result.output
    assert "update stuff" in result.output
    assert "unknown_commit_policy" in result.output


def test_unknown_commit_error_policy_blocks_bump(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
unknown_commit_policy = "error"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "update stuff")
    result = runner.invoke(app, ["bump"])
    assert result.exit_code == 1
    # File untouched
    assert 'version = "1.2.0"' in (repo / "pyproject.toml").read_text()


def test_status_since_overrides_commit_window(repo: Path, runner: CliRunner):
    # First commit lives "before" the override; second is "after" it.
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: pre-baseline change")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: in-window change")

    # Default since (per-component last tag = none) sees both commits
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "pre-baseline" in result.output
    assert "in-window" in result.output

    # --since <sha> only sees the in-window commit
    result = runner.invoke(app, ["status", "--since", sha])
    assert result.exit_code == 0
    assert "pre-baseline" not in result.output
    assert "in-window" in result.output


def test_plan_since_overrides_commit_window(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: pre")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: post")

    result = runner.invoke(
        app, ["plan", "--since", sha, "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    api = payload["bumps"]["api"]
    # Only the fix landed in the window -> patch, not minor
    assert api["kind"] == "patch"
    [reason] = [r for r in api["reasons"] if r["kind"] == "commit"]
    assert reason["subject"] == "post"


def test_explain_since_overrides_commit_window(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: ignored")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, {"src/main.py": "x = 3\n"}, "fix: kept")

    result = runner.invoke(app, ["explain", "api", "--since", sha])
    assert result.exit_code == 0
    assert "kept" in result.output
    assert "ignored" not in result.output


def test_changed_text_output_lists_changed_components(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    result = runner.invoke(app, ["changed"])
    assert result.exit_code == 0, result.stdout
    # api was touched; chart wasn't (but chart is empty in the fixture; the
    # mirror cascade is a release concept, not a "changed" one)
    assert "api" in result.stdout.split()


def test_changed_json_includes_unchanged(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    result = runner.invoke(app, ["changed", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "api" in payload["changed"]
    assert "chart" in payload["unchanged"]


def test_changed_against_explicit_since(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: api change")
    _commit(repo, {"charts/myapp/values.yaml": "y: 1\n"}, "feat: chart change")
    # baseline: HEAD before the two new commits = the init commit
    sha = _git(repo, "rev-list", "--max-parents=0", "HEAD").strip()

    result = runner.invoke(
        app, ["changed", "--since", sha, "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload["changed"]) == {"api", "chart"}


def test_changed_excludes_release_commits(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    runner.invoke(app, ["bump", "--commit", "--tag"])  # creates a chore(release): commit

    # No new content commits since the tag — only the release commit.
    # Use --since on the init commit to span the entire history.
    sha = _git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    result = runner.invoke(
        app, ["changed", "--since", sha, "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # api genuinely changed (the feat commit). The chore(release) commit
    # touched pyproject.toml too but was filtered out.
    assert "api" in payload["changed"]


def test_changed_returns_nothing_when_idle(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["changed", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["changed"] == []
    assert set(payload["unchanged"]) == {"api", "chart"}


def test_artifacts_text_output(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[[components.api.artifacts]]
type = "docker"
ref = "ghcr.io/foo/api:{version}"

[[components.api.artifacts]]
type = "docker"
ref = "registry.acme.com/api:{version}"
""")
    result = runner.invoke(app, ["artifacts", "api"])
    assert result.exit_code == 0, result.stdout
    assert "ghcr.io/foo/api:1.2.0" in result.output
    assert "registry.acme.com/api:1.2.0" in result.output


def test_artifacts_json_output(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[[components.api.artifacts]]
type = "docker"
ref = "ghcr.io/foo/api:{version}"
""")
    result = runner.invoke(app, ["artifacts", "api", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["api"]["version"] == "1.2.0"
    [artifact] = payload["api"]["artifacts"]
    assert artifact == {"type": "docker", "ref": "ghcr.io/foo/api:1.2.0"}


def test_artifacts_explicit_version(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[[components.api.artifacts]]
type = "docker"
ref = "ghcr.io/foo/api:{version}"
""")
    result = runner.invoke(app, ["artifacts", "api", "--version", "9.9.9"])
    assert result.exit_code == 0
    assert "ghcr.io/foo/api:9.9.9" in result.output


def test_artifacts_all_components(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[[components.api.artifacts]]
type = "docker"
ref = "ghcr.io/foo/api:{version}"

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]

[[components.chart.artifacts]]
type = "helm"
ref = "{component}-{version}.tgz"
""")
    result = runner.invoke(app, ["artifacts", "--all", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["api"]["artifacts"][0]["ref"] == "ghcr.io/foo/api:1.2.0"
    assert payload["chart"]["artifacts"][0]["ref"] == "chart-0.4.0.tgz"


def test_artifacts_arg_required(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["artifacts"])
    assert result.exit_code == 1


def test_plan_json_includes_artifacts(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]

[[components.api.artifacts]]
type = "docker"
ref = "ghcr.io/foo/api:{version}"

[components.chart]
paths = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]

[[components.chart.artifacts]]
type = "helm"
ref = "{component}-{version}.tgz"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    result = runner.invoke(app, ["plan", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    api = payload["bumps"]["api"]
    assert api["next_version"] == "1.3.0"
    assert api["artifacts"] == [{"type": "docker", "ref": "ghcr.io/foo/api:1.3.0"}]
    chart = payload["bumps"]["chart"]
    assert chart["artifacts"] == [{"type": "helm", "ref": "chart-0.4.1.tgz"}]


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


def test_bump_pep440_scheme_writes_canonical_form(repo: Path, runner: CliRunner):
    # api uses pep440 scheme; chart keeps semver default
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]
version_scheme = "pep440"

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add login")
    result = runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    assert result.exit_code == 0, result.stdout

    # api: PEP 440 canonical
    assert 'version = "1.3.0rc1"' in (repo / "pyproject.toml").read_text()
    # The mirror writes the same pep440 form into Chart.yaml:appVersion
    chart_yaml = (repo / "charts/myapp/Chart.yaml").read_text()
    assert "appVersion: 1.3.0rc1" in chart_yaml

    # tag is also rendered in pep440 form for api
    tags = _git(repo, "tag").split()
    assert "api-v1.3.0rc1" in tags
    # chart keeps its own (default semver) scheme
    assert any(t.startswith("chart-v") for t in tags)


def test_bump_pep440_scheme_finalizes_correctly(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
version_scheme = "pep440"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    runner.invoke(app, ["bump", "--pre", "rc", "--commit", "--tag"])
    assert 'version = "1.3.0rc1"' in (repo / "pyproject.toml").read_text()

    runner.invoke(app, ["bump", "--finalize", "--commit", "--tag"])
    assert 'version = "1.3.0"' in (repo / "pyproject.toml").read_text()


def _capture_git_args(monkeypatch):
    """Spy that captures every (cwd, args) pair passed to subprocess.run
    for git, while still letting the real subprocess execute (so the
    write side-effects happen).

    Signed `git commit -S` and `git tag -s` are stubbed: CI runners
    don't have GPG configured, so the real call would fail and short-
    circuit the rest of the bump pipeline before we can capture later
    args. We only care about the arguments here, not the side effects.
    """
    import subprocess as real_subprocess
    captured: list[list[str]] = []
    real_run = real_subprocess.run

    def spy(args, *posargs, **kwargs):
        if args and args[0] == "git":
            captured.append(list(args[1:]))
            if len(args) > 1 and args[1] in ("commit", "tag") and (
                "-S" in args or "-s" in args
            ):
                return real_subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, *posargs, **kwargs)

    monkeypatch.setattr("multicz.cli.subprocess.run", spy)
    return captured


def test_bump_sign_passes_signing_flags_to_git(
    repo: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    captured = _capture_git_args(monkeypatch)
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")

    # Use --sign — the real `git commit -S` will likely fail in CI without
    # GPG, but we're inspecting the *args*, not the result.
    runner.invoke(app, ["bump", "--commit", "--tag", "--sign"])

    # The fixture setup uses `git commit -q` and `git tag -m` directly, so
    # filter to the release commit/tag (those don't include -q from us, and
    # the tag args carry -s/-m without --list).
    release_commit = [
        args for args in captured
        if args[:1] == ["commit"] and "-q" not in args
    ]
    release_tag = [
        args for args in captured
        if args[:1] == ["tag"] and "--list" not in args and "-d" not in args
    ]
    assert release_commit and "-S" in release_commit[0]
    assert release_tag and "-s" in release_tag[0]


def test_bump_default_does_not_pass_signing_flags(
    repo: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    captured = _capture_git_args(monkeypatch)
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    runner.invoke(app, ["bump", "--commit", "--tag"])

    release_commit = [
        args for args in captured
        if args[:1] == ["commit"] and "-q" not in args
    ]
    release_tag = [
        args for args in captured
        if args[:1] == ["tag"] and "--list" not in args and "-d" not in args
    ]
    assert release_commit and "-S" not in release_commit[0]
    assert release_tag and "-s" not in release_tag[0]


def test_config_sign_commits_enables_signing(
    repo: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
sign_commits = true
""")
    captured = _capture_git_args(monkeypatch)
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    runner.invoke(app, ["bump", "--commit"])

    release_commit = [
        args for args in captured
        if args[:1] == ["commit"] and "-q" not in args
    ]
    assert release_commit and "-S" in release_commit[0]


def test_config_sign_tags_only_signs_tags(
    repo: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
sign_tags = true
""")
    captured = _capture_git_args(monkeypatch)
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    runner.invoke(app, ["bump", "--commit", "--tag"])

    release_commit = [
        args for args in captured
        if args[:1] == ["commit"] and "-q" not in args
    ]
    release_tag = [
        args for args in captured
        if args[:1] == ["tag"] and "--list" not in args and "-d" not in args
    ]
    # commit not signed, tag signed
    assert release_commit and "-S" not in release_commit[0]
    assert release_tag and "-s" in release_tag[0]


def test_bump_force_creates_bump_without_commits(repo: Path, runner: CliRunner):
    """--force bumps a component even when no commits would normally trigger it."""
    result = runner.invoke(app, ["bump", "--force", "api:patch"])
    assert result.exit_code == 0, result.stdout
    assert 'version = "1.2.1"' in (repo / "pyproject.toml").read_text()


def test_bump_force_repeatable(repo: Path, runner: CliRunner):
    result = runner.invoke(
        app, ["bump", "--force", "api:minor", "--force", "chart:major"]
    )
    assert result.exit_code == 0, result.stdout
    assert 'version = "1.3.0"' in (repo / "pyproject.toml").read_text()
    chart = (repo / "charts/myapp/Chart.yaml").read_text()
    assert "version: 1.0.0" in chart  # major bump


def test_bump_force_promotes_existing_bump(repo: Path, runner: CliRunner):
    """Force-major over a feat (which would be minor) wins."""
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    result = runner.invoke(app, ["bump", "--force", "api:major"])
    assert result.exit_code == 0
    assert 'version = "2.0.0"' in (repo / "pyproject.toml").read_text()


def test_bump_force_does_not_demote(repo: Path, runner: CliRunner):
    """Force-patch when commits already imply minor doesn't downgrade."""
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    result = runner.invoke(app, ["bump", "--force", "api:patch"])
    assert result.exit_code == 0
    # feat is minor, force patch is weaker, minor wins
    assert 'version = "1.3.0"' in (repo / "pyproject.toml").read_text()


def test_bump_force_invalid_kind(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["bump", "--force", "api:weird"])
    assert result.exit_code == 1
    assert "invalid kind" in result.output


def test_bump_force_unknown_component(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["bump", "--force", "nope:patch"])
    assert result.exit_code == 1
    assert "unknown component" in result.output


def test_bump_force_invalid_spec(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["bump", "--force", "no-colon"])
    assert result.exit_code == 1
    assert "invalid --force spec" in result.output


def test_bump_force_composes_with_pre(repo: Path, runner: CliRunner):
    result = runner.invoke(
        app, ["bump", "--force", "api:minor", "--pre", "rc"]
    )
    assert result.exit_code == 0, result.stdout
    assert 'version = "1.3.0-rc.1"' in (repo / "pyproject.toml").read_text()


def test_plan_force_shows_manual_reason(repo: Path, runner: CliRunner):
    result = runner.invoke(
        app, ["plan", "--force", "api:patch", "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    api = payload["bumps"]["api"]
    assert api["next_version"] == "1.2.1"
    [reason] = api["reasons"]
    assert reason["kind"] == "manual"
    assert "force" in reason["note"]


def test_empty_plan_message_mentions_force(repo: Path, runner: CliRunner):
    result = runner.invoke(app, ["bump"])
    assert result.exit_code == 0
    assert "--force" in result.output


def test_release_commit_message_template_components(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
release_commit_message = "chore(release): {components}"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    runner.invoke(app, ["bump", "--commit", "--tag"])

    head_msg = _git(repo, "log", "-1", "--format=%B").strip()
    assert head_msg == "chore(release): api v1.3.0, chart v0.4.1"


def test_release_commit_message_template_count(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
release_commit_message = "release: {count} components ({summary})"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    runner.invoke(app, ["bump", "--commit", "--tag"])

    head_msg = _git(repo, "log", "-1", "--format=%B").strip()
    assert head_msg.startswith("release: 2 components")
    assert "api 1.2.0 -> 1.3.0" in head_msg


def test_release_commit_message_default_unchanged(repo: Path, runner: CliRunner):
    """Without override the historical format must be preserved exactly."""
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    runner.invoke(app, ["bump", "--commit", "--tag"])

    head_msg = _git(repo, "log", "-1", "--format=%B").strip()
    assert head_msg.startswith(
        "chore(release): bump api 1.2.0 -> 1.3.0, chart 0.4.0 -> 0.4.1"
    )
    # default body is the bullet list
    assert "- api: 1.2.0 -> 1.3.0 (minor)" in head_msg
    assert "- chart: 0.4.0 -> 0.4.1 (patch)" in head_msg


def test_bump_commit_message_cli_override(repo: Path, runner: CliRunner):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    result = runner.invoke(
        app,
        ["bump", "--commit", "--tag", "--commit-message", "release: my custom message"],
    )
    assert result.exit_code == 0, result.stdout

    head_msg = _git(repo, "log", "-1", "--format=%B").strip()
    assert head_msg == "release: my custom message"


def test_bump_commit_message_requires_commit(repo: Path, runner: CliRunner):
    result = runner.invoke(
        app, ["bump", "--commit-message", "ignored without --commit"]
    )
    assert result.exit_code == 1
    assert "--commit" in result.output


def test_release_commit_message_template_with_literal_braces(repo: Path, runner: CliRunner):
    (repo / "multicz.toml").write_text(CONFIG + """
[project]
release_commit_message = "release {{json}} for {components}"
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat(api): add login")
    runner.invoke(app, ["bump", "--commit", "--tag"])

    head_msg = _git(repo, "log", "-1", "--format=%B").strip()
    assert head_msg == "release {json} for api v1.3.0, chart v0.4.1"


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


def test_init_print_emits_to_stdout_without_writing(tmp_path: Path, runner: CliRunner):
    target = tmp_path / "fresh"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "auto-app"\nversion = "0.1.0"\n'
    )
    (target / "src").mkdir()
    os.chdir(target)
    result = runner.invoke(app, ["init", "--print"])
    assert result.exit_code == 0
    assert "[components.auto-app]" in result.stdout
    # Filesystem untouched
    assert not (target / "multicz.toml").exists()


def test_init_print_bare(tmp_path: Path, runner: CliRunner):
    os.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--print", "--bare"])
    assert result.exit_code == 0
    assert "[components.app]" in result.stdout
    assert not (tmp_path / "multicz.toml").exists()


def test_init_detect_text_summary(tmp_path: Path, runner: CliRunner):
    target = tmp_path / "fresh"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "auto-app"\nversion = "0.1.0"\n'
    )
    os.chdir(target)
    result = runner.invoke(app, ["init", "--detect"])
    assert result.exit_code == 0
    assert "Detected" in result.output
    assert "auto-app" in result.output
    assert not (target / "multicz.toml").exists()


def test_init_detect_json_output(tmp_path: Path, runner: CliRunner):
    target = tmp_path / "fresh"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\nversion = "1.0.0"\n'
    )
    os.chdir(target)
    result = runner.invoke(app, ["init", "--detect", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "myapp" in payload
    assert payload["myapp"]["bump_files"][0]["key"] == "project.version"


def test_init_detect_rejects_bare(tmp_path: Path, runner: CliRunner):
    os.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--detect", "--bare"])
    assert result.exit_code == 1
    assert "cannot be combined" in result.output


def test_init_detect_rejects_print(tmp_path: Path, runner: CliRunner):
    target = tmp_path / "fresh"
    target.mkdir()
    (target / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    os.chdir(target)
    result = runner.invoke(app, ["init", "--detect", "--print"])
    assert result.exit_code == 1


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


def test_post_bump_runs_command_and_includes_modified_file(
    repo: Path, runner: CliRunner
):
    """post_bump runs after writes and pulls modified files into the
    release commit (simulates `uv lock` regenerating uv.lock)."""
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
post_bump = ["sh -c 'echo regenerated > generated.lock'"]
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    result = runner.invoke(app, ["bump", "--commit"])
    assert result.exit_code == 0, result.stdout

    # The lockfile produced by the hook is committed alongside pyproject.
    head_files = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert "generated.lock" in head_files
    assert "pyproject.toml" in head_files
    assert (repo / "generated.lock").read_text().strip() == "regenerated"


def test_post_bump_failure_aborts_bump(
    repo: Path, runner: CliRunner
):
    """A non-zero post_bump exit aborts the bump pipeline before
    committing or tagging — the working tree may have been written to,
    but no release commit is created."""
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
post_bump = ["false"]
""")
    head_before = _git(repo, "rev-parse", "HEAD").strip()
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    result = runner.invoke(app, ["bump", "--commit", "--tag"])
    assert result.exit_code != 0
    head_after_feat = _git(repo, "rev-parse", "HEAD").strip()
    # No `chore(release)` commit landed on top of the feat commit.
    assert head_after_feat != head_before  # the feat commit did land
    assert "chore(release)" not in _git(repo, "log", "-1", "--format=%s")


def test_post_bump_skipped_in_dry_run(
    repo: Path, runner: CliRunner
):
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
post_bump = ["sh -c 'echo nope > should_not_exist.lock'"]
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    runner.invoke(app, ["bump", "--dry-run"])
    assert not (repo / "should_not_exist.lock").exists()


def test_post_bump_includes_file_already_dirty_before_hook(
    repo: Path, runner: CliRunner
):
    """Reproduces the `uv run` race: uv (or some pre-bump tool)
    rewrites a lockfile before multicz starts, so the file is already
    in the dirty set when multicz takes its `before` snapshot. The
    hook then rewrites it again with different content. A pure set
    diff would miss it; the hash comparison catches it."""
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
post_bump = ["sh -c 'echo final > preexisting.lock'"]
""")
    # Pre-write the lockfile so it's already dirty when multicz starts
    # (mimics `uv run` re-syncing uv.lock before multicz code executes).
    (repo / "preexisting.lock").write_text("stale\n")
    _git(repo, "add", "preexisting.lock")
    _git(repo, "commit", "-q", "-m", "chore: seed lock")
    (repo / "preexisting.lock").write_text("intermediate\n")  # dirty
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    # Re-dirty after _commit (which `git add -A`'d the lock above).
    (repo / "preexisting.lock").write_text("intermediate\n")

    result = runner.invoke(app, ["bump", "--commit"])
    assert result.exit_code == 0, result.stdout

    head_files = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert "preexisting.lock" in head_files
    # The committed content is the *hook output*, not the intermediate.
    committed = _git(repo, "show", "HEAD:preexisting.lock").strip()
    assert committed == "final"


def test_post_bump_runs_only_for_bumped_components(
    repo: Path, runner: CliRunner
):
    """Hooks fire only for components that actually got bumped — a
    component with `post_bump` that didn't change must stay quiet."""
    (repo / "multicz.toml").write_text("""
[components.api]
paths = ["src/**"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[components.untouched]
paths = ["docs/**"]
bump_files = [{ file = "docs/version.txt", key = "" }]
post_bump = ["sh -c 'echo ran > untouched.lock'"]
""")
    (repo / "docs").mkdir()
    (repo / "docs/version.txt").write_text("0.0.1\n")
    _commit(repo, {"docs/.gitkeep": ""}, "chore: keep")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: x")
    runner.invoke(app, ["bump"])
    assert not (repo / "untouched.lock").exists()
