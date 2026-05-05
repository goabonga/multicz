# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

import pytest

from multicz.formats import FormatError
from multicz.formats.properties import PropertiesFormat


def test_matches_only_for_dotted_extension(tmp_path: Path):
    fmt = PropertiesFormat()
    assert fmt.matches(tmp_path / "gradle.properties", "version")
    assert not fmt.matches(tmp_path / "pyproject.toml", "version")
    assert not fmt.matches(tmp_path / "gradle.properties", None)


def test_read_value_with_equals(tmp_path: Path):
    f = tmp_path / "gradle.properties"
    f.write_text("version=1.2.3\n")
    assert PropertiesFormat().read(f, "version") == "1.2.3"


def test_read_value_with_colon_separator(tmp_path: Path):
    f = tmp_path / "gradle.properties"
    f.write_text("version : 1.2.3\n")
    assert PropertiesFormat().read(f, "version") == "1.2.3"


def test_read_skips_comments_and_blanks(tmp_path: Path):
    f = tmp_path / "gradle.properties"
    f.write_text(
        "# header comment\n"
        "! pling-style comment\n"
        "\n"
        "version=1.2.3\n"
    )
    assert PropertiesFormat().read(f, "version") == "1.2.3"


def test_read_supports_dotted_keys_verbatim(tmp_path: Path):
    """In .properties files, ``a.b.c`` is one verbatim key, not nested."""
    f = tmp_path / "application.properties"
    f.write_text("server.port=8080\nserver.timeout=30\n")
    assert PropertiesFormat().read(f, "server.port") == "8080"
    assert PropertiesFormat().read(f, "server.timeout") == "30"


def test_read_missing_key_raises(tmp_path: Path):
    f = tmp_path / "gradle.properties"
    f.write_text("foo=bar\n")
    with pytest.raises(FormatError, match="not found"):
        PropertiesFormat().read(f, "version")


def test_write_preserves_comments_and_other_keys(tmp_path: Path):
    f = tmp_path / "gradle.properties"
    f.write_text(
        "# top comment\n"
        "kotlin.version=1.9.0\n"
        "version=1.0.0\n"
        "# trailer\n"
    )
    PropertiesFormat().write(f, "version", "2.0.0")
    text = f.read_text()
    assert "# top comment\n" in text
    assert "kotlin.version=1.9.0\n" in text
    assert "version=2.0.0\n" in text
    assert "# trailer\n" in text


def test_write_appends_when_key_missing(tmp_path: Path):
    f = tmp_path / "gradle.properties"
    f.write_text("foo=bar\n")
    PropertiesFormat().write(f, "version", "1.0.0")
    assert f.read_text() == "foo=bar\nversion=1.0.0\n"
