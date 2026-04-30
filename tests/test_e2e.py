"""End-to-end planner tests against a real on-disk git repository."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from multicz.config import load_config
from multicz.planner import build_plan

CONFIG = """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
"""

INITIAL_FILES = {
    "multicz.toml": CONFIG,
    "pyproject.toml": '[project]\nname = "x"\nversion = "1.2.0"\n',
    "src/main.py": "x = 1\n",
    "charts/myapp/Chart.yaml": (
        "apiVersion: v2\nname: x\nversion: 0.4.0\nappVersion: 1.2.0\n"
    ),
    "charts/myapp/templates/deployment.yaml": "kind: Deployment\n",
}


def _git(repo: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed ({result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


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
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _commit(tmp_path, INITIAL_FILES, "chore: init")
    return tmp_path


def test_feat_on_api_cascades_to_chart(repo: Path):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: add stuff")

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert set(plan.bumps) == {"api", "chart"}
    assert plan.bumps["api"].kind == "minor"
    assert str(plan.bumps["api"].next) == "1.3.0"
    assert plan.bumps["chart"].kind == "patch"
    assert str(plan.bumps["chart"].next) == "0.4.1"


def test_template_only_change_does_not_bump_api(repo: Path):
    _commit(
        repo,
        {"charts/myapp/templates/deployment.yaml": "kind: Deployment\nfoo: bar\n"},
        "fix(chart): tweak deployment",
    )

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert "api" not in plan.bumps
    assert plan.bumps["chart"].kind == "patch"
    assert str(plan.bumps["chart"].next) == "0.4.1"


def test_breaking_bumps_major(repo: Path):
    _commit(repo, {"src/main.py": "x = 99\n"}, "feat!: drop py3.11 support")

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert plan.bumps["api"].kind == "major"
    assert str(plan.bumps["api"].next) == "2.0.0"
    assert plan.bumps["chart"].kind == "patch"


def test_release_commits_are_skipped(repo: Path):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: real change")
    _commit(repo, {"src/main.py": "x = 3\n"}, "chore(release): bump api 1.2.0 -> 1.3.0")

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert plan.bumps["api"].kind == "minor"
    assert "real change" in " ".join(plan.bumps["api"].reasons)
    assert "release" not in " ".join(plan.bumps["api"].reasons).lower()


def test_chart_only_change_after_api_tag(repo: Path):
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: api change")
    _git(repo, "tag", "-m", "api 1.3.0", "api-v1.3.0")
    _git(repo, "tag", "-m", "chart 0.4.1", "chart-v0.4.1")
    _commit(
        repo,
        {"charts/myapp/templates/deployment.yaml": "kind: Deployment\nx: 1\n"},
        "fix(chart): scale tweak",
    )

    plan = build_plan(repo, load_config(repo / "multicz.toml"))

    assert "api" not in plan.bumps
    assert plan.bumps["chart"].kind == "patch"
    assert str(plan.bumps["chart"].current) == "0.4.1"
    assert str(plan.bumps["chart"].next) == "0.4.2"
