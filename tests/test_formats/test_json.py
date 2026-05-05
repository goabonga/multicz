# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

import pytest

from multicz.formats import FormatError
from multicz.formats.json import JsonFormat


def test_matches_json_extension_only(tmp_path: Path):
    fmt = JsonFormat()
    assert fmt.matches(tmp_path / "package.json", "version")
    assert not fmt.matches(tmp_path / "package.json", None)
    assert not fmt.matches(tmp_path / "Chart.yaml", "version")


def test_read_navigates_dotted_path(tmp_path: Path):
    f = tmp_path / "package.json"
    f.write_text('{"name": "myapp", "version": "1.2.3"}\n')
    assert JsonFormat().read(f, "version") == "1.2.3"


def test_write_preserves_detected_indent_2(tmp_path: Path):
    f = tmp_path / "package.json"
    f.write_text(
        '{\n'
        '  "name": "myapp",\n'
        '  "version": "1.0.0"\n'
        '}\n'
    )
    JsonFormat().write(f, "version", "2.0.0")
    text = f.read_text()
    assert '"version": "2.0.0"' in text
    assert '  "name"' in text  # still 2-space indent


def test_write_preserves_detected_indent_4(tmp_path: Path):
    f = tmp_path / "package.json"
    f.write_text(
        '{\n'
        '    "name": "myapp",\n'
        '    "version": "1.0.0"\n'
        '}\n'
    )
    JsonFormat().write(f, "version", "2.0.0")
    text = f.read_text()
    assert '    "version": "2.0.0"' in text  # 4-space indent preserved


def test_write_creates_intermediate_objects(tmp_path: Path):
    f = tmp_path / "package.json"
    f.write_text("{}\n")
    JsonFormat().write(f, "scripts.test", "pytest")
    text = f.read_text()
    assert '"scripts"' in text and '"test": "pytest"' in text


def test_write_handles_empty_file(tmp_path: Path):
    """Edge case: empty file should be treated as `{}`."""
    f = tmp_path / "package.json"
    f.write_text("")
    JsonFormat().write(f, "version", "1.0.0")
    assert '"version": "1.0.0"' in f.read_text()


def test_read_missing_key_raises(tmp_path: Path):
    f = tmp_path / "package.json"
    f.write_text('{"name": "myapp"}\n')
    with pytest.raises(FormatError, match="not found"):
        JsonFormat().read(f, "version")
