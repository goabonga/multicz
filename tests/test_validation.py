# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for the validate sanity checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from multicz.config import load_config
from multicz.validation import Finding, validate


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "x@y")
    _git(tmp_path, "config", "user.name", "x")
    return tmp_path


def _write_config(repo: Path, body: str) -> None:
    (repo / "multicz.toml").write_text(body)


def _commit_all(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "test")


def _checks(findings: list[Finding]) -> set[str]:
    return {f.check for f in findings}


# ----------------------------------------------------------------------
# bump_files existence
# ----------------------------------------------------------------------


def test_bump_file_existing_passes(repo: Path):
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    _write_config(repo, """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    assert "bump_files_exist" not in _checks(findings)


def test_missing_bump_file_is_error(repo: Path):
    _write_config(repo, """
[components.api]
paths = ["src/**"]
bump_files = [{ file = "missing.toml", key = "version" }]
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    errors = [f for f in findings if f.check == "bump_files_exist"]
    assert errors
    assert errors[0].level == "error"
    assert errors[0].component == "api"


# ----------------------------------------------------------------------
# path overlap
# ----------------------------------------------------------------------


def _overlap_repo(repo: Path, policy: str | None = None) -> None:
    """Common fixture: api and lib both claim src/**."""
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("x = 1\n")
    project_block = (
        f'\n[project]\noverlap_policy = "{policy}"\n' if policy else ""
    )
    _write_config(repo, project_block + """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[components.lib]
paths = ["src/**"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
""")
    _commit_all(repo)


def test_path_overlap_default_is_error(repo: Path):
    _overlap_repo(repo)  # default: overlap_policy = "error"

    findings = validate(repo, load_config(repo / "multicz.toml"))
    overlaps = [f for f in findings if f.check == "path_overlap"]
    assert overlaps
    assert overlaps[0].level == "error"
    assert overlaps[0].component == "lib"  # 'api' wins (declared first)


def test_path_overlap_first_match_warns(repo: Path):
    _overlap_repo(repo, policy="first-match")

    findings = validate(repo, load_config(repo / "multicz.toml"))
    overlaps = [f for f in findings if f.check == "path_overlap"]
    assert overlaps and overlaps[0].level == "warning"


def test_path_overlap_allow_silent(repo: Path):
    _overlap_repo(repo, policy="allow")

    findings = validate(repo, load_config(repo / "multicz.toml"))
    assert all(f.check != "path_overlap" for f in findings)


def test_path_overlap_all_is_info(repo: Path):
    _overlap_repo(repo, policy="all")

    findings = validate(repo, load_config(repo / "multicz.toml"))
    overlaps = [f for f in findings if f.check == "path_overlap"]
    assert overlaps and overlaps[0].level == "info"


# ----------------------------------------------------------------------
# mirror target classification
# ----------------------------------------------------------------------


def test_mirror_to_unowned_file_is_info(repo: Path):
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    (repo / "values.yaml").write_text("foo: bar\n")
    _write_config(repo, """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "values.yaml", key = "version" }]
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    assert "mirror_target_unowned" in _checks(findings)


def test_mirror_to_self_owned_file_is_warning(repo: Path):
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    _write_config(repo, """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "pyproject.toml", key = "project.version" }]
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    selfish = [f for f in findings if f.check == "mirror_self_target"]
    assert selfish
    assert selfish[0].level == "warning"


# ----------------------------------------------------------------------
# trigger and mirror cycles
# ----------------------------------------------------------------------


def test_trigger_cycle_detected(repo: Path):
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    _write_config(repo, """
[components.a]
paths = ["a/**"]
triggers = ["b"]

[components.b]
paths = ["b/**"]
triggers = ["a"]
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    cycles = [f for f in findings if f.check == "trigger_cycle"]
    assert cycles
    assert cycles[0].level == "error"
    assert "->" in cycles[0].message


def test_mirror_cycle_detected(repo: Path):
    (repo / "a.yaml").write_text("v: 1\n")
    (repo / "b.yaml").write_text("v: 1\n")
    _write_config(repo, """
[components.a]
paths = ["a.yaml"]
bump_files = [{ file = "a.yaml", key = "v" }]
mirrors = [{ file = "b.yaml", key = "v" }]

[components.b]
paths = ["b.yaml"]
bump_files = [{ file = "b.yaml", key = "v" }]
mirrors = [{ file = "a.yaml", key = "v" }]
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    cycles = [f for f in findings if f.check == "mirror_cycle"]
    assert cycles
    assert cycles[0].level == "error"


# ----------------------------------------------------------------------
# changelog paths
# ----------------------------------------------------------------------


def test_changelog_path_is_a_directory_is_error(repo: Path):
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    (repo / "CHANGELOG.md").mkdir()  # dir, not a file
    _write_config(repo, """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
changelog = "CHANGELOG.md"
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    bad = [f for f in findings if f.check == "changelog_not_a_file"]
    assert bad
    assert bad[0].level == "error"


# ----------------------------------------------------------------------
# debian/changelog
# ----------------------------------------------------------------------


def test_debian_changelog_missing_is_info(repo: Path):
    _write_config(repo, """
[components.mypkg]
paths = ["debian/**"]
format = "debian"
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    assert "debian_changelog_missing" in _checks(findings)


def test_debian_changelog_unparseable_is_error(repo: Path):
    debian = repo / "debian"
    debian.mkdir()
    (debian / "changelog").write_text("not a debian changelog\n")
    _write_config(repo, """
[components.mypkg]
paths = ["debian/**"]
format = "debian"
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    bad = [f for f in findings if f.check == "debian_changelog_unparseable"]
    assert bad
    assert bad[0].level == "error"


def test_debian_changelog_parseable_passes(repo: Path):
    debian = repo / "debian"
    debian.mkdir()
    (debian / "changelog").write_text(
        "mypkg (1.2.3-1) unstable; urgency=medium\n\n"
        "  * Initial.\n\n"
        " -- x <x@y>  Sun, 01 Jan 2023 00:00:00 +0000\n"
    )
    _write_config(repo, """
[components.mypkg]
paths = ["debian/**"]
format = "debian"
""")
    findings = validate(repo, load_config(repo / "multicz.toml"))
    debian_findings = [f for f in findings if "debian" in f.check]
    assert all(f.level != "error" for f in debian_findings)


# ----------------------------------------------------------------------
# clean repo
# ----------------------------------------------------------------------


def test_clean_repo_no_findings(repo: Path):
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\nversion = "1.0.0"\n'
    )
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("x = 1\n")
    _write_config(repo, """
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
changelog = "CHANGELOG.md"
""")
    _commit_all(repo)
    findings = validate(repo, load_config(repo / "multicz.toml"))
    assert findings == []
