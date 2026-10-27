# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Edge cases of the git helpers: missing git, bad ranges, odd tag names."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from multicz.commits import git as git_mod
from multicz.commits.git import (
    GitError,
    commits_in_range,
    latest_stable_tag,
    latest_tag,
    previous_stable_tag,
    previous_tag,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "tag.gpgsign", "false")
    (tmp_path / "f.txt").write_text("x")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-q", "-m", "feat: first")
    return tmp_path


def test_missing_git_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(git_mod.subprocess, "run", boom)
    with pytest.raises(GitError, match="git executable not found"):
        git_mod._run_git(["status"], tmp_path)


def test_failing_git_reports_exit_code(tmp_path: Path) -> None:
    with pytest.raises(GitError, match=r"failed \(exit \d+\)"):
        git_mod._run_git(["rev-parse", "HEAD"], tmp_path)


def test_commits_in_range_with_unknown_revision_is_empty(repo: Path) -> None:
    assert commits_in_range(repo, "no-such-tag", "HEAD") == []


def test_tag_lookups_skip_unparsable_versions(repo: Path) -> None:
    _git(repo, "tag", "v1.0.0")
    _git(repo, "tag", "vnot-a-version")
    assert latest_tag(repo, "v") == "v1.0.0"
    assert latest_stable_tag(repo, "v") == "v1.0.0"
    assert previous_tag(repo, "v", "v1.0.0") is None


def test_tag_lookups_skip_glob_only_matches(repo: Path) -> None:
    # ``?`` is a glob wildcard: git lists ``xv1.0.0`` for the pattern ``?v*``
    # but the tag does not literally start with the prefix.
    _git(repo, "tag", "xv1.0.0")
    assert latest_tag(repo, "?v") is None
    assert latest_stable_tag(repo, "?v") is None
    assert previous_tag(repo, "?v", "?v2.0.0") is None


def test_latest_stable_tag_ignores_prereleases(repo: Path) -> None:
    _git(repo, "tag", "v1.0.0")
    _git(repo, "tag", "v1.1.0rc1")
    assert latest_tag(repo, "v") == "v1.1.0rc1"
    assert latest_stable_tag(repo, "v") == "v1.0.0"


def test_previous_stable_tag_skips_prereleases(repo: Path) -> None:
    _git(repo, "tag", "v1.0.0")
    _git(repo, "tag", "v1.1.0rc1")
    _git(repo, "tag", "v1.1.0")
    assert previous_tag(repo, "v", "v1.1.0") == "v1.1.0rc1"
    assert previous_stable_tag(repo, "v", "v1.1.0") == "v1.0.0"


def test_previous_tag_with_unparsable_current(repo: Path) -> None:
    _git(repo, "tag", "v1.0.0")
    assert previous_tag(repo, "v", "vgarbage") is None
