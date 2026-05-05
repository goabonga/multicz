# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

import pytest

from multicz.formats import FormatError
from multicz.formats.toml import TomlFormat


def test_matches_for_toml_extension_only(tmp_path: Path):
    fmt = TomlFormat()
    assert fmt.matches(tmp_path / "pyproject.toml", "project.version")
    assert not fmt.matches(tmp_path / "pyproject.toml", None)
    assert not fmt.matches(tmp_path / "package.json", "project.version")


def test_read_navigates_dotted_path(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[project]\n'
        'name = "myapp"\n'
        'version = "1.2.3"\n'
    )
    assert TomlFormat().read(f, "project.version") == "1.2.3"


def test_write_preserves_comments_and_neighbour_keys(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '# leading comment\n'
        '[project]\n'
        'name = "myapp"  # inline\n'
        'version = "1.0.0"\n'
    )
    TomlFormat().write(f, "project.version", "2.0.0")
    text = f.read_text()
    assert "# leading comment" in text
    assert 'name = "myapp"  # inline' in text
    assert 'version = "2.0.0"' in text


def test_write_creates_intermediate_tables(tmp_path: Path):
    f = tmp_path / "x.toml"
    f.write_text('# empty\n')
    TomlFormat().write(f, "deeply.nested.version", "1.0.0")
    text = f.read_text()
    assert "1.0.0" in text


def test_read_missing_key_raises(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    f.write_text('[project]\nname = "myapp"\n')
    with pytest.raises(FormatError, match="not found"):
        TomlFormat().read(f, "project.version")
