# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

from multicz.formats.properties import PropertiesFormat


def test_properties_write_skips_lines_without_equals(tmp_path: Path):
    f = tmp_path / "a.properties"
    f.write_text("# c\n\nfoo: bar\nversion=1\n")
    PropertiesFormat().write(f, "version", "2")
    assert f.read_text() == "# c\n\nfoo: bar\nversion=2\n"


def test_properties_write_replaces_last_line_without_newline(tmp_path: Path):
    f = tmp_path / "a.properties"
    f.write_text("version=1")
    PropertiesFormat().write(f, "version", "2")
    assert f.read_text() == "version=2\n"


def test_properties_write_appends_after_unterminated_line(tmp_path: Path):
    f = tmp_path / "a.properties"
    f.write_text("other=1")
    PropertiesFormat().write(f, "version", "2")
    assert f.read_text() == "other=1\nversion=2\n"
