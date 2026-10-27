# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Edge cases of ``build_plan``: writer-claimed versions, mirrors, --force."""

from __future__ import annotations

import subprocess
from pathlib import Path

from multicz.config import load_config
from multicz.planner import build_plan


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)


def _init_repo(tmp_path: Path, config: str, extra: dict[str, str] | None = None) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    files = {
        "multicz.toml": config,
        "pyproject.toml": '[project]\nname = "x"\nversion = "1.0.0"\n',
        "src/main.py": "x = 1\n",
    }
    files.update(extra or {})
    _commit(tmp_path, files, "chore: init")
    return tmp_path


def test_invalid_writer_version_falls_back_to_initial_version(tmp_path: Path):
    cfg = """
[components.pkg]
paths = ["src/**", "debian/**"]

[[components.pkg.writers]]
type = "debian-changelog"
"""
    changelog = (
        "pkg (not.a.version) unstable; urgency=low\n\n  * x\n\n"
        " -- A <a@b.c>  Mon, 15 Jan 2024 12:34:56 +0000\n"
    )
    repo = _init_repo(tmp_path, cfg, {"debian/changelog": changelog})
    _commit(repo, {"src/main.py": "x = 2\n"}, "fix: something")

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert (
        str(plan.bumps["pkg"].current) == load_config(repo / "multicz.toml").project.initial_version
    )


def test_mirror_to_unowned_file_does_not_cascade(tmp_path: Path):
    cfg = """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [
  { file = "values.yaml", key = "version" },
  { file = "pyproject.toml", key = "project.version" },
]
"""
    repo = _init_repo(tmp_path, cfg, {"values.yaml": "version: 1\n"})
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: new thing")

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert list(plan.bumps) == ["api"]
    assert plan.bumps["api"].kind == "minor"


def test_force_ignores_unknown_component(tmp_path: Path):
    cfg = """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
"""
    repo = _init_repo(tmp_path, cfg)

    plan = build_plan(
        repo, load_config(repo / "multicz.toml"), force={"ghost": "major", "api": "patch"}
    )

    assert list(plan.bumps) == ["api"]
    assert plan.bumps["api"].kind == "patch"
