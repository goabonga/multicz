# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

from multicz.config.sources import PyprojectSource


def test_metadata():
    src = PyprojectSource()
    assert src.name == "pyproject"
    assert src.filename == "pyproject.toml"


def test_extract_reads_tool_multicz_table(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[project]\n'
        'name = "myapp"\n'
        'version = "1.0.0"\n'
        '\n'
        '[tool.multicz.project]\n'
        'commit_convention = "conventional"\n'
        '\n'
        '[tool.multicz.components.api]\n'
        'paths = ["src/**"]\n'
        'bump_files = [{ file = "pyproject.toml", key = "project.version" }]\n'
    )
    raw = PyprojectSource().extract(f)
    assert raw is not None
    assert raw["project"]["commit_convention"] == "conventional"
    assert raw["components"]["api"]["paths"] == ["src/**"]


def test_extract_returns_none_when_no_tool_multicz_section(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[project]\n'
        'name = "myapp"\n'
        '[tool.ruff]\n'
        'line-length = 100\n'
    )
    assert PyprojectSource().extract(f) is None


def test_extract_returns_none_when_no_tool_table(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    f.write_text('[project]\nname = "myapp"\n')
    assert PyprojectSource().extract(f) is None


def test_extract_returns_none_when_tool_multicz_is_not_a_table(tmp_path: Path):
    """Defensive: if the user wrote `[tool] multicz = "..."` instead of
    `[tool.multicz]`, extract returns None rather than raising."""
    f = tmp_path / "pyproject.toml"
    f.write_text('[tool]\nmulticz = "scalar value"\n')
    assert PyprojectSource().extract(f) is None


def test_extract_returns_none_when_file_missing(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    assert PyprojectSource().extract(f) is None


def test_extract_returns_none_on_malformed_toml(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    f.write_text("[unclosed\n")
    assert PyprojectSource().extract(f) is None


def test_extract_isolates_tool_multicz_from_other_tool_subtables(tmp_path: Path):
    """The [tool.foo] tables of other tools must NOT leak into the
    extracted multicz section."""
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[tool.ruff]\n'
        'line-length = 100\n'
        '\n'
        '[tool.multicz.project]\n'
        'tag_format = "v{version}"\n'
    )
    raw = PyprojectSource().extract(f)
    assert raw is not None
    assert "ruff" not in raw  # only the [tool.multicz] subtree
    assert raw["project"]["tag_format"] == "v{version}"
