# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

from multicz.formats.plain import PlainFormat


def test_matches_only_when_key_is_none(tmp_path: Path):
    fmt = PlainFormat()
    f = tmp_path / "VERSION"
    f.touch()
    assert fmt.matches(f, None)
    assert not fmt.matches(f, "project.version")
    assert not fmt.matches(f, "regex:foo")


def test_read_strips_surrounding_whitespace(tmp_path: Path):
    f = tmp_path / "VERSION"
    f.write_text("  1.2.3\n\n")
    assert PlainFormat().read(f, None) == "1.2.3"


def test_write_appends_trailing_newline(tmp_path: Path):
    f = tmp_path / "VERSION"
    f.write_text("0.0.0\n")
    PlainFormat().write(f, None, "1.0.0")
    assert f.read_text() == "1.0.0\n"


def test_write_overwrites_existing_content(tmp_path: Path):
    f = tmp_path / "VERSION"
    f.write_text("1.0.0\n# unrelated comment\n")
    PlainFormat().write(f, None, "2.0.0")
    # Plain mode treats the whole file as the value — no preservation.
    assert f.read_text() == "2.0.0\n"
