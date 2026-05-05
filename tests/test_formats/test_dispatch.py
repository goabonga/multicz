# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Tests covering the cross-format dispatch order in `formats/__init__.py`.

Per-format behaviour is covered in the sibling files; this one verifies
that when several handlers *could* match the same `(file, key)` pair,
the right one wins (the order documented in `FORMATS`).
"""

from pathlib import Path

import pytest

from multicz.formats import FORMATS, FormatError, read_value, write_value


def test_regex_handler_overrides_extension_dispatch(tmp_path: Path):
    """A `regex:` key on a `.toml` file uses regex, not toml-dotted lookup."""
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[project]\n'
        'name = "myapp"\n'
        'version = "1.2.3"\n'
    )
    # Same file, regex key against the `version` literal — bypasses
    # tomlkit and edits the bytes directly via the regex handler.
    assert read_value(f, r'regex:version = "([^"]+)"') == "1.2.3"
    write_value(f, r'regex:version = "([^"]+)"', "9.9.9")
    assert read_value(f, "project.version") == "9.9.9"


def test_plain_handler_used_when_key_is_none_even_for_known_extensions(tmp_path: Path):
    """`key=None` on a `.json` file means "treat as plain", not "parse JSON"."""
    f = tmp_path / "weird.json"
    f.write_text("just a string\n")
    # PlainFormat matches before JsonFormat in the registry.
    assert read_value(f, None) == "just a string"


def test_unknown_extension_with_key_raises(tmp_path: Path):
    f = tmp_path / "weird.xml"
    f.write_text("<root/>")
    with pytest.raises(FormatError, match="no format handler"):
        read_value(f, "root.version")


def test_write_raises_when_file_missing(tmp_path: Path):
    f = tmp_path / "does-not-exist.toml"
    with pytest.raises(FormatError, match="does not exist"):
        write_value(f, "project.version", "1.0.0")


def test_registry_order_is_stable():
    """The first match wins — order encodes precedence rules."""
    names = [fmt.name for fmt in FORMATS]
    # regex MUST come before any extension-based format so it overrides.
    assert names.index("regex") < names.index("toml")
    # plain MUST come before extension-based formats so `key=None` wins.
    assert names.index("plain") < names.index("toml")
