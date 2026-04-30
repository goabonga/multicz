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

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
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
    assert "_No changes._" in result.stdout


def test_init_writes_starter_config(tmp_path: Path, runner: CliRunner):
    target = tmp_path / "fresh"
    target.mkdir()
    os.chdir(target)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (target / "multicz.toml").exists()
