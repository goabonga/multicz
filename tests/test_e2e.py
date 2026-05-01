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
    summaries = " ".join(plan.bumps["api"].reason_summaries())
    assert "real change" in summaries
    assert "release" not in summaries.lower()


def test_ignored_types_project_level_skips_commit_entirely(repo: Path):
    cfg = repo / "multicz.toml"
    cfg.write_text("""
[project]
ignored_types = ["chore", "ci"]

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat: real change")
    _commit(repo, {"src/main.py": "x = 3\n"}, "chore(deps): bump typer")
    _commit(repo, {"src/main.py": "x = 4\n"}, "ci: tweak workflow")

    plan = build_plan(repo, load_config(cfg))
    assert plan.bumps["api"].kind == "minor"
    summaries = " ".join(plan.bumps["api"].reason_summaries())
    assert "real change" in summaries
    assert "chore(deps)" not in summaries
    assert "ci:" not in summaries


def test_ignored_types_component_level(repo: Path):
    cfg = repo / "multicz.toml"
    cfg.write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
ignored_types = ["fix"]

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
""")
    _commit(
        repo,
        {"src/main.py": "x = 2\n", "charts/myapp/values.yaml": "x: 1\n"},
        "fix: cross cutting bug",
    )
    plan = build_plan(repo, load_config(cfg))
    # api ignores 'fix' -> not in plan
    assert "api" not in plan.bumps
    # chart still patches
    assert plan.bumps["chart"].kind == "patch"


def test_ignored_types_unioned(repo: Path):
    cfg = repo / "multicz.toml"
    cfg.write_text("""
[project]
ignored_types = ["docs"]

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
ignored_types = ["fix"]
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "fix: filtered-by-component")
    _commit(repo, {"src/main.py": "x = 3\n"}, "docs: filtered-by-project")
    _commit(repo, {"src/main.py": "x = 4\n"}, "feat: kept")
    plan = build_plan(repo, load_config(cfg))
    summaries = " ".join(plan.bumps["api"].reason_summaries())
    assert "filtered-by-component" not in summaries
    assert "filtered-by-project" not in summaries
    assert "kept" in summaries


def test_ignored_types_does_not_drop_breaking_commits_implicitly(repo: Path):
    """If `feat` is ignored, even feat! is filtered out — explicit user choice."""
    cfg = repo / "multicz.toml"
    cfg.write_text("""
[project]
ignored_types = ["feat"]

[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    _commit(repo, {"src/main.py": "x = 2\n"}, "feat!: drop py3.11")
    plan = build_plan(repo, load_config(cfg))
    assert "api" not in plan.bumps  # ignored even though it's breaking


def test_bump_policy_default_propagates_kind_to_every_touched_component(repo: Path):
    """A feat commit touching both api and chart files bumps both as minor."""
    _commit(
        repo,
        {
            "src/main.py": "x = 2\n",
            "charts/myapp/values.yaml": "x: 1\n",
        },
        "feat: change API contract and update Helm values",
    )

    plan = build_plan(repo, load_config(repo / "multicz.toml"))
    assert plan.bumps["api"].kind == "minor"
    assert plan.bumps["chart"].kind == "minor"


def test_bump_policy_scoped_demotes_minor_to_patch_for_other_components(repo: Path):
    """With scoped policy, a feat(api) touching chart files only patches chart."""
    cfg = repo / "multicz.toml"
    cfg.write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
bump_policy = "scoped"
""")
    _commit(
        repo,
        {
            "src/main.py": "x = 2\n",
            "charts/myapp/values.yaml": "x: 1\n",
        },
        "feat(api): change API contract and update Helm values",
    )

    plan = build_plan(repo, load_config(cfg))
    assert plan.bumps["api"].kind == "minor"  # scope matches api
    assert plan.bumps["chart"].kind == "patch"  # demoted: scope=api != chart

    # Demotion is recorded on the CommitReason
    chart_commit_reasons = [
        r for r in plan.bumps["chart"].reasons
        if r.__class__.__name__ == "CommitReason"
    ]
    assert chart_commit_reasons[0].original_kind == "minor"
    assert chart_commit_reasons[0].bump_kind == "patch"


def test_bump_policy_scoped_no_scope_propagates_normally(repo: Path):
    """Commits without a scope are NOT demoted under scoped policy — no scope
    means 'applies broadly' rather than 'doesn't apply to me'."""
    cfg = repo / "multicz.toml"
    cfg.write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
bump_policy = "scoped"
""")
    _commit(
        repo,
        {
            "src/main.py": "x = 2\n",
            "charts/myapp/values.yaml": "x: 1\n",
        },
        "feat: cross-cutting change",
    )

    plan = build_plan(repo, load_config(cfg))
    assert plan.bumps["api"].kind == "minor"
    assert plan.bumps["chart"].kind == "minor"  # no scope -> not demoted


def test_bump_policy_scoped_matching_scope_keeps_kind(repo: Path):
    """feat(chart): ... on a scoped chart component keeps the minor kind."""
    cfg = repo / "multicz.toml"
    cfg.write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
bump_policy = "scoped"
""")
    _commit(
        repo,
        {"charts/myapp/values.yaml": "x: 1\n"},
        "feat(chart): add new value",
    )

    plan = build_plan(repo, load_config(cfg))
    assert "api" not in plan.bumps  # api files not touched
    assert plan.bumps["chart"].kind == "minor"  # scope matches chart


def test_per_component_tag_format_is_honored(repo: Path):
    # Re-write the config with a tag_format override on api only
    cfg = repo / "multicz.toml"
    cfg.write_text("""
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]
tag_format = "api-{version}"

[components.chart]
paths = ["charts/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
""")

    # Existing tags from a previous release cycle
    _git(repo, "tag", "-m", "api 1.4.0", "api-1.4.0")
    _git(repo, "tag", "-m", "chart 0.7.0", "chart-v0.7.0")

    # New commit after the tags so there's something to bump
    _commit(
        repo,
        {"src/main.py": "x = 2\n", "charts/myapp/values.yaml": "x: 1\n"},
        "feat: add stuff",
    )

    plan = build_plan(repo, load_config(cfg))

    # api's current version is read from "api-1.4.0" via the OVERRIDE prefix
    # ("api-"), not from a default "api-v…" tag (which does not exist here).
    assert str(plan.bumps["api"].current) == "1.4.0"
    assert str(plan.bumps["chart"].current) == "0.7.0"
    assert str(plan.bumps["api"].next) == "1.5.0"


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
