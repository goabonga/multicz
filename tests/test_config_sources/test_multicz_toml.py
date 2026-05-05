# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for `MulticzTomlSource`.

Integration coverage of the dispatch path lives in `tests/test_config.py`;
this file pokes at the source class directly to exercise edge cases
without going through `load_config` / `find_config`.
"""

from pathlib import Path

from multicz.config.sources import MulticzTomlSource


def test_metadata():
    src = MulticzTomlSource()
    assert src.name == "multicz-toml"
    assert src.filename == "multicz.toml"


def test_extract_returns_full_document(tmp_path: Path):
    f = tmp_path / "multicz.toml"
    f.write_text(
        '[project]\n'
        'commit_convention = "conventional"\n'
        'tag_format = "v{version}"\n'
    )
    raw = MulticzTomlSource().extract(f)
    assert raw is not None
    assert raw["project"]["tag_format"] == "v{version}"


def test_extract_empty_file_returns_empty_dict(tmp_path: Path):
    """A blank but valid TOML file is still a valid config (no project,
    no components — the schema validator decides if that's acceptable)."""
    f = tmp_path / "multicz.toml"
    f.write_text("")
    assert MulticzTomlSource().extract(f) == {}


def test_extract_returns_none_when_file_missing(tmp_path: Path):
    f = tmp_path / "multicz.toml"
    # File never created — extract() must NOT raise.
    assert MulticzTomlSource().extract(f) is None


def test_extract_returns_none_on_malformed_toml(tmp_path: Path):
    f = tmp_path / "multicz.toml"
    f.write_text("[unclosed_table\nfoo = bar\n")
    assert MulticzTomlSource().extract(f) is None


def test_extract_preserves_nested_structures(tmp_path: Path):
    f = tmp_path / "multicz.toml"
    f.write_text(
        '[components.api]\n'
        'paths = ["src/**", "pyproject.toml"]\n'
        'bump_files = [{ file = "pyproject.toml", key = "project.version" }]\n'
    )
    raw = MulticzTomlSource().extract(f)
    assert raw is not None
    api = raw["components"]["api"]
    assert api["paths"] == ["src/**", "pyproject.toml"]
    assert api["bump_files"][0]["file"] == "pyproject.toml"
