# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz bump``: git failures, hooks, plugin gate, push, helper edges."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.exceptions import Exit
from typer.testing import CliRunner

from multicz.cli import app
from multicz.cli.commands import bump as bump_module
from multicz.cli.commands.bump import (
    _git as bump_git,
)
from multicz.cli.commands.bump import (
    _hash_file,
    _porcelain_paths,
    _run_post_bump_hook,
)

BASE = """
[components.lib]
paths = ["lib/**"]
bump_files = [{ file = "lib/v.toml", key = "version" }]

[components.app]
paths = ["app/**"]
bump_files = [{ file = "app/v.toml", key = "version" }]
"""


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


def _init(repo: Path, config: str) -> None:
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _commit(
        repo,
        {
            "multicz.toml": config,
            "lib/v.toml": 'version = "1.0.0"\n',
            "app/v.toml": 'version = "2.0.0"\n',
        },
        "chore: init",
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _init(tmp_path, BASE)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_component_filter_limits_the_bump(repo: Path):
    _commit(repo, {"lib/a.py": "1\n", "app/a.py": "1\n"}, "feat: both")
    result = CliRunner().invoke(app, ["bump", "--component", "lib"])
    assert result.exit_code == 0, result.output
    assert 'version = "1.1.0"' in (repo / "lib/v.toml").read_text()
    assert 'version = "2.0.0"' in (repo / "app/v.toml").read_text()


def test_failing_git_command_aborts_with_message(repo: Path):
    _commit(repo, {"lib/a.py": "1\n"}, "feat: thing")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    result = CliRunner().invoke(app, ["bump", "--commit"])
    assert result.exit_code == 1
    assert "failed" in result.output


def test_push_pushes_commit_and_tags(repo: Path, tmp_path_factory: pytest.TempPathFactory):
    remote = tmp_path_factory.mktemp("remote")
    _git(remote, "init", "-q", "--bare", "-b", "main")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "main")
    _commit(repo, {"lib/a.py": "1\n"}, "feat: thing")
    result = CliRunner().invoke(app, ["bump", "--commit", "--tag", "--push"])
    assert result.exit_code == 0, result.output
    assert "lib-v1.1.0" in _git(remote, "tag")


def test_head_lookup_failure_does_not_block_state_file(repo: Path, monkeypatch: pytest.MonkeyPatch):
    (repo / "multicz.toml").write_text(BASE + '\n[project]\nstate_file = ".multicz/state.json"\n')
    _git(repo, "commit", "-q", "-a", "-m", "chore: state")
    _commit(repo, {"lib/a.py": "1\n"}, "feat: thing")

    def fake_git(repo_arg: Path, *args: str) -> str:
        if args[:2] == ("rev-parse", "HEAD"):
            raise Exit(code=1)
        return bump_git(repo_arg, *args)

    monkeypatch.setattr(bump_module, "_git", fake_git)
    result = CliRunner().invoke(app, ["bump"])
    assert result.exit_code == 0, result.output
    assert (repo / ".multicz" / "state.json").is_file()


def test_post_bump_hooks_skipped_when_policy_denies(repo: Path):
    (repo / "multicz.toml").write_text(
        BASE.replace('paths = ["lib/**"]', 'paths = ["lib/**"]\npost_bump = ["true"]')
    )
    _git(repo, "commit", "-q", "-a", "-m", "chore: hook")
    _commit(repo, {"lib/a.py": "1\n"}, "feat: thing")
    result = CliRunner().invoke(app, ["bump"])
    assert result.exit_code == 0, result.output
    assert "post_bump hooks skipped" in result.output


def test_post_plan_errors_abort_the_bump(repo: Path):
    config = BASE + '\n[plugins.deprecation]\nscan = ["lib/*.py"]\n'
    (repo / "multicz.toml").write_text(config)
    _git(repo, "commit", "-q", "-a", "-m", "chore: plugin")
    _commit(
        repo,
        {"lib/a.py": "# DEPRECATED since=0.5.0 remove_in=1.1.0 - drop me\n"},
        "feat: thing",
    )
    result = CliRunner().invoke(app, ["bump"])
    assert result.exit_code == 1
    assert "must be removed by 1.1.0" in result.output
    assert 'version = "1.0.0"' in (repo / "lib/v.toml").read_text()


def test_run_post_bump_hook_ignores_blank_command(tmp_path: Path):
    _run_post_bump_hook(tmp_path, "")


def test_run_post_bump_hook_failure_prints_stderr(tmp_path: Path, capsys: pytest.CaptureFixture):
    with pytest.raises(Exit):
        _run_post_bump_hook(tmp_path, "sh -c 'echo oops >&2; exit 3'")
    assert "oops" in capsys.readouterr().err


def test_hash_file_missing_returns_none(tmp_path: Path):
    assert _hash_file(tmp_path / "missing") is None


def test_porcelain_paths_outside_a_repo_is_empty(tmp_path: Path):
    assert _porcelain_paths(tmp_path) == set()


def test_porcelain_paths_parses_short_lines_and_renames(monkeypatch: pytest.MonkeyPatch):
    fake = SimpleNamespace(returncode=0, stdout="ab\nR  old.txt -> new.txt\n M plain.txt\n")
    monkeypatch.setattr(bump_module.subprocess, "run", lambda *a, **k: fake)
    assert _porcelain_paths(Path(".")) == {"new.txt", "plain.txt"}
