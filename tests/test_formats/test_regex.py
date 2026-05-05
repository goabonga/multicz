# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for `RegexFormat` in isolation.

End-to-end coverage of the dispatch path lives in `test_writers.py`;
this file pokes at the format class directly to verify edge cases
without going through `read_value` / `write_value`.
"""

from pathlib import Path

import pytest

from multicz.formats import FormatError
from multicz.formats.regex import RegexFormat


def test_matches_only_when_key_starts_with_regex_prefix(tmp_path: Path):
    fmt = RegexFormat()
    f = tmp_path / "anything.toml"
    f.touch()
    assert fmt.matches(f, "regex:foo")
    assert not fmt.matches(f, "project.version")
    assert not fmt.matches(f, None)


def test_read_returns_first_capture_group(tmp_path: Path):
    f = tmp_path / "src.py"
    f.write_text('__version__ = "1.2.3"\n')
    assert RegexFormat().read(f, r'regex:^__version__\s*=\s*"([^"]+)"') == "1.2.3"


def test_read_raises_on_no_match(tmp_path: Path):
    f = tmp_path / "src.py"
    f.write_text("nothing here\n")
    with pytest.raises(FormatError, match="matched nothing"):
        RegexFormat().read(f, r'regex:^__version__\s*=\s*"([^"]+)"')


def test_write_replaces_only_first_match(tmp_path: Path):
    f = tmp_path / "src.py"
    f.write_text('VERSION = "1.0.0"\n# also: VERSION = "old" in comments\n')
    RegexFormat().write(f, r'regex:VERSION\s*=\s*"([^"]+)"', "2.0.0")
    text = f.read_text()
    assert 'VERSION = "2.0.0"' in text
    # Second occurrence in the comment stays untouched.
    assert '"old"' in text


def test_write_preserves_surrounding_bytes(tmp_path: Path):
    """Quotes, indentation, trailing comments — all preserved verbatim."""
    f = tmp_path / "Makefile"
    f.write_text('VERSION := 1.0.0  # set by hand\n')
    RegexFormat().write(f, r'regex:^VERSION\s*:=\s*(\S+)', "2.0.0")
    assert f.read_text() == 'VERSION := 2.0.0  # set by hand\n'


def test_empty_pattern_raises(tmp_path: Path):
    f = tmp_path / "x"
    f.touch()
    with pytest.raises(FormatError, match="empty regex pattern"):
        RegexFormat().read(f, "regex:")


def test_pattern_without_capture_group_raises(tmp_path: Path):
    f = tmp_path / "x"
    f.write_text("VERSION = 1.0.0\n")
    with pytest.raises(FormatError, match="capture group"):
        RegexFormat().read(f, r"regex:VERSION = .*")


def test_invalid_regex_raises(tmp_path: Path):
    f = tmp_path / "x"
    f.touch()
    with pytest.raises(FormatError, match="invalid regex"):
        RegexFormat().read(f, r"regex:(unclosed")
