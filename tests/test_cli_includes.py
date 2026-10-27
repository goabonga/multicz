# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""The commands run unchanged on a config split across component files."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multicz.cli import app

runner = CliRunner()

FILES = {
    "multicz.toml": '[[component.path]]\npath = "packages/*"\n',
    "packages/lib/multicz.component.toml": (
        '[components.lib]\nchangelog = "CHANGELOG.md"\n'
        'bump_files = [{ file = "version.json", key = "version" }]\n'
    ),
    "packages/lib/version.json": '{"version": "1.0.0"}\n',
    "packages/app/multicz.component.toml": (
        '[components.app]\ndepends_on = ["lib"]\nchangelog = "CHANGELOG.md"\n'
        'bump_files = [{ file = "version.json", key = "version" }]\n'
    ),
    "packages/app/version.json": '{"version": "2.0.0"}\n',
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout


def _commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit(tmp_path, FILES, "chore: init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_validate_accepts_the_split_config(repo: Path):
    assert runner.invoke(app, ["validate", "--strict"]).exit_code == 0


def test_a_change_in_one_directory_bumps_only_its_component(repo: Path):
    _commit(repo, {"packages/lib/mod.py": "x = 1\n"}, "fix(lib): correct the lookup")
    result = runner.invoke(app, ["plan", "--output", "json"])
    assert result.exit_code == 0
    bumps = json.loads(result.output)["bumps"]
    assert set(bumps) == {"lib", "app"}
    assert bumps["lib"]["next_version"] == "1.0.1"


def test_depends_on_cascades_across_files(repo: Path):
    _commit(repo, {"packages/lib/mod.py": "x = 1\n"}, "feat(lib): add a lookup")
    result = runner.invoke(app, ["plan", "--output", "json"])
    bumps = json.loads(result.output)["bumps"]
    assert bumps["app"]["next_version"] == "2.0.1"


def test_bump_writes_the_rebased_files(repo: Path):
    _commit(repo, {"packages/lib/mod.py": "x = 1\n"}, "feat(lib): add a lookup")
    result = runner.invoke(app, ["bump", "--commit"])
    assert result.exit_code == 0, result.output
    assert json.loads((repo / "packages/lib/version.json").read_text())["version"] == "1.1.0"
    assert json.loads((repo / "packages/app/version.json").read_text())["version"] == "2.0.1"
    assert "1.1.0" in (repo / "packages/lib/CHANGELOG.md").read_text()
    assert (repo / "packages/app/CHANGELOG.md").is_file()
    assert not (repo / "CHANGELOG.md").exists()


def test_running_from_inside_a_package_finds_the_root(repo: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(repo / "packages/app")
    assert runner.invoke(app, ["validate", "--strict"]).exit_code == 0


def test_config_source_lists_every_file(repo: Path):
    result = runner.invoke(app, ["config", "--source", "-c", "app"])
    assert result.exit_code == 0
    # The console wraps long paths; compare without whitespace.
    output = "".join(result.output.split())
    for name in (
        "multicz.toml",
        "packages/app/multicz.component.toml",
        "packages/lib/multicz.component.toml",
    ):
        assert name in output


MIXED = {
    "multicz.toml": (
        '[[component.path]]\npath = "packages/*"\n'
        '[components.core]\npaths = ["core/**"]\ndepends_on = ["lib"]\n'
        'bump_files = [{ file = "core/version.json", key = "version" }]\n'
    ),
    "core/version.json": '{"version": "3.0.0"}\n',
    "packages/lib/multicz.component.toml": (
        '[components.lib]\nbump_files = [{ file = "version.json", key = "version" }]\n'
    ),
    "packages/lib/version.json": '{"version": "1.0.0"}\n',
    "packages/app/multicz.component.toml": (
        '[components.app]\ndepends_on = ["core"]\n'
        'bump_files = [{ file = "version.json", key = "version" }]\n'
    ),
    "packages/app/version.json": '{"version": "2.0.0"}\n',
}


@pytest.fixture
def mixed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """``core`` (root) depends on ``lib`` (merged); ``app`` (merged) on ``core``."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit(tmp_path, MIXED, "chore: init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _planned(output: str) -> dict[str, str]:
    return {n: b["next_version"] for n, b in json.loads(output)["bumps"].items()}


def test_a_merged_component_cascades_into_a_root_one_and_on_to_a_merged_one(mixed: Path):
    _commit(mixed, {"packages/lib/mod.py": "x = 1\n"}, "feat(lib): add a lookup")
    result = runner.invoke(app, ["plan", "--output", "json"])
    assert result.exit_code == 0, result.output
    assert _planned(result.output) == {"lib": "1.1.0", "core": "3.0.1", "app": "2.0.1"}


def test_a_root_component_cascades_into_a_merged_one_only(mixed: Path):
    _commit(mixed, {"core/mod.py": "x = 1\n"}, "fix(core): correct the core")
    result = runner.invoke(app, ["plan", "--output", "json"])
    assert _planned(result.output) == {"core": "3.0.1", "app": "2.0.1"}


def test_a_leaf_merged_component_cascades_nowhere(mixed: Path):
    _commit(mixed, {"packages/app/mod.py": "x = 1\n"}, "feat(app): add a flag")
    result = runner.invoke(app, ["plan", "--output", "json"])
    assert _planned(result.output) == {"app": "2.1.0"}


def test_the_cascade_is_written_to_the_rebased_files(mixed: Path):
    _commit(mixed, {"packages/lib/mod.py": "x = 1\n"}, "feat(lib): add a lookup")
    assert runner.invoke(app, ["bump", "--commit"]).exit_code == 0
    versions = {
        name: json.loads((mixed / path).read_text())["version"]
        for name, path in {
            "lib": "packages/lib/version.json",
            "core": "core/version.json",
            "app": "packages/app/version.json",
        }.items()
    }
    assert versions == {"lib": "1.1.0", "core": "3.0.1", "app": "2.0.1"}


def test_a_dependency_cycle_across_root_and_merged_files_is_reported(mixed: Path):
    _commit(
        mixed,
        {
            "packages/lib/multicz.component.toml": (
                '[components.lib]\ndepends_on = ["app"]\n'
                'bump_files = [{ file = "version.json", key = "version" }]\n'
            )
        },
        "chore: make lib depend on app",
    )
    result = runner.invoke(app, ["validate", "--strict"])
    assert result.exit_code != 0
    assert "trigger cycle" in result.output
