# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

import json
from pathlib import Path

from multicz.config.sources import PackageJsonSource


def test_metadata():
    src = PackageJsonSource()
    assert src.name == "package-json"
    assert src.filename == "package.json"


def test_extract_reads_top_level_multicz_key(tmp_path: Path):
    f = tmp_path / "package.json"
    f.write_text(json.dumps({
        "name": "monorepo",
        "version": "1.0.0",
        "multicz": {
            "project": {"commit_convention": "conventional"},
            "components": {
                "web": {
                    "paths": ["src/**"],
                    "bump_files": [{"file": "package.json", "key": "version"}],
                },
            },
        },
    }))
    raw = PackageJsonSource().extract(f)
    assert raw is not None
    assert raw["project"]["commit_convention"] == "conventional"
    assert raw["components"]["web"]["paths"] == ["src/**"]


def test_extract_returns_none_when_no_multicz_key(tmp_path: Path):
    f = tmp_path / "package.json"
    f.write_text(json.dumps({"name": "x", "version": "1.0.0"}))
    assert PackageJsonSource().extract(f) is None


def test_extract_returns_none_when_multicz_is_null(tmp_path: Path):
    """Defensive: `"multicz": null` is not a dict — must not crash."""
    f = tmp_path / "package.json"
    f.write_text(json.dumps({"multicz": None}))
    assert PackageJsonSource().extract(f) is None


def test_extract_returns_none_when_multicz_is_a_string(tmp_path: Path):
    """Same with `"multicz": "something"`."""
    f = tmp_path / "package.json"
    f.write_text(json.dumps({"multicz": "scalar"}))
    assert PackageJsonSource().extract(f) is None


def test_extract_returns_none_when_root_is_an_array(tmp_path: Path):
    """A package.json whose top-level is `[...]` instead of `{...}`."""
    f = tmp_path / "package.json"
    f.write_text(json.dumps([1, 2, 3]))
    assert PackageJsonSource().extract(f) is None


def test_extract_returns_none_when_file_missing(tmp_path: Path):
    f = tmp_path / "package.json"
    assert PackageJsonSource().extract(f) is None


def test_extract_returns_none_on_malformed_json(tmp_path: Path):
    f = tmp_path / "package.json"
    f.write_text('{"name": "x",,,}')
    assert PackageJsonSource().extract(f) is None
