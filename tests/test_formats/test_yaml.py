# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from pathlib import Path

import pytest

from multicz.formats import FormatError
from multicz.formats.yaml import YamlFormat


def test_matches_yaml_and_yml_extensions(tmp_path: Path):
    fmt = YamlFormat()
    assert fmt.matches(tmp_path / "Chart.yaml", "version")
    assert fmt.matches(tmp_path / "values.yml", "image.tag")
    assert not fmt.matches(tmp_path / "Chart.yaml", None)
    assert not fmt.matches(tmp_path / "Chart.json", "version")


def test_read_navigates_dotted_path(tmp_path: Path):
    f = tmp_path / "Chart.yaml"
    f.write_text(
        "apiVersion: v2\n"
        "name: myapp\n"
        "version: 1.2.3\n"
        "appVersion: 0.5.0\n"
    )
    assert YamlFormat().read(f, "version") == "1.2.3"
    assert YamlFormat().read(f, "appVersion") == "0.5.0"


def test_write_preserves_comments_and_quoting(tmp_path: Path):
    f = tmp_path / "Chart.yaml"
    f.write_text(
        "# Helm chart for myapp\n"
        "apiVersion: v2\n"
        'name: "myapp"  # quoted\n'
        "version: 1.0.0\n"
    )
    YamlFormat().write(f, "version", "2.0.0")
    text = f.read_text()
    assert "# Helm chart for myapp" in text
    assert 'name: "myapp"  # quoted' in text
    assert "version: 2.0.0" in text


def test_write_nested_key(tmp_path: Path):
    f = tmp_path / "values.yaml"
    f.write_text(
        "image:\n"
        "  repository: ghcr.io/x/y\n"
        "  tag: 1.0.0\n"
    )
    YamlFormat().write(f, "image.tag", "2.0.0")
    text = f.read_text()
    assert "tag: 2.0.0" in text
    assert "repository: ghcr.io/x/y" in text


def test_read_missing_key_raises(tmp_path: Path):
    f = tmp_path / "Chart.yaml"
    f.write_text("apiVersion: v2\nname: myapp\n")
    with pytest.raises(FormatError, match="not found"):
        YamlFormat().read(f, "version")
