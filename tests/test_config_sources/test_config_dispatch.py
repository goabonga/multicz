# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cross-source dispatch tests for `load_config` / `find_config`.

Per-source `extract` behaviour is covered in the sibling files. This
one focuses on how the orchestrator resolves precedence when several
candidates coexist.
"""

import json
from pathlib import Path

import pytest

from multicz.config.sources import (
    CONFIG_SOURCES,
    PackageJsonSource,
    PyprojectSource,
    _source_for,
    find_config,
    load_config,
)

MINIMAL_CONFIG = {
    "project": {"commit_convention": "conventional"},
    "components": {
        "app": {
            "paths": ["src/**"],
            "bump_files": [{"file": "pyproject.toml", "key": "project.version"}],
        },
    },
}


def test_source_for_dispatches_by_filename(tmp_path: Path):
    assert _source_for(tmp_path / "multicz.toml").name == "multicz-toml"
    assert _source_for(tmp_path / "pyproject.toml").name == "pyproject"
    assert _source_for(tmp_path / "package.json").name == "package-json"
    # Unknown filename → no source claims it.
    assert _source_for(tmp_path / "Cargo.toml") is None


def test_registry_order_is_canonical_first():
    """multicz.toml (canonical) must come before fallbacks so a
    standalone config file always wins over an embedded section."""
    names = [src.name for src in CONFIG_SOURCES]
    assert names[0] == "multicz-toml"
    assert "pyproject" in names[1:]
    assert "package-json" in names[1:]


def test_load_config_via_multicz_toml(tmp_path: Path):
    f = tmp_path / "multicz.toml"
    f.write_text(
        '[project]\n'
        'commit_convention = "conventional"\n'
        '[components.app]\n'
        'paths = ["src/**"]\n'
        'bump_files = [{ file = "pyproject.toml", key = "project.version" }]\n'
    )
    config = load_config(f)
    assert "app" in config.components


def test_load_config_via_pyproject(tmp_path: Path):
    f = tmp_path / "pyproject.toml"
    f.write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
        '[tool.multicz.project]\ncommit_convention = "conventional"\n'
        '[tool.multicz.components.app]\n'
        'paths = ["src/**"]\n'
        'bump_files = [{ file = "pyproject.toml", key = "project.version" }]\n'
    )
    config = load_config(f)
    assert "app" in config.components


def test_load_config_via_package_json(tmp_path: Path):
    f = tmp_path / "package.json"
    f.write_text(json.dumps({"name": "x", "version": "1.0.0", "multicz": MINIMAL_CONFIG}))
    config = load_config(f)
    assert "app" in config.components


def test_load_config_raises_on_unknown_filename(tmp_path: Path):
    f = tmp_path / "Cargo.toml"
    f.write_text("[package]\nname = \"x\"\n")
    with pytest.raises(FileNotFoundError, match="no multicz config"):
        load_config(f)


def test_find_config_prefers_multicz_toml_over_pyproject(tmp_path: Path):
    """When both files coexist in the same directory, multicz.toml wins."""
    canonical = tmp_path / "multicz.toml"
    canonical.write_text(
        '[components.from_canonical]\n'
        'paths = ["src/**"]\n'
        'bump_files = [{ file = "pyproject.toml", key = "project.version" }]\n'
    )
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        '[tool.multicz.components.from_pyproject]\n'
        'paths = ["src/**"]\n'
        'bump_files = [{ file = "pyproject.toml", key = "project.version" }]\n'
    )

    assert find_config(tmp_path) == canonical


def test_find_config_falls_back_to_pyproject_when_no_canonical(tmp_path: Path):
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        '[tool.multicz.components.app]\n'
        'paths = ["src/**"]\n'
        'bump_files = [{ file = "pyproject.toml", key = "project.version" }]\n'
    )
    assert find_config(tmp_path) == pyproj


def test_find_config_skips_pyproject_without_tool_multicz(tmp_path: Path):
    """A pyproject.toml with no [tool.multicz] table must not be claimed —
    `find_config` keeps walking instead of treating it as found."""
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text('[project]\nname = "x"\n')
    with pytest.raises(FileNotFoundError):
        find_config(tmp_path)


def test_find_config_walks_up_to_parent_directory(tmp_path: Path):
    """When no candidate is found in the start dir, walk up the tree."""
    sub = tmp_path / "subdir"
    sub.mkdir()
    (tmp_path / "multicz.toml").write_text(
        '[components.app]\n'
        'paths = ["src/**"]\n'
        'bump_files = [{ file = "pyproject.toml", key = "project.version" }]\n'
    )
    assert find_config(sub) == tmp_path / "multicz.toml"


def test_protocol_compliance():
    """Every entry in CONFIG_SOURCES exposes the documented attributes."""
    for src in CONFIG_SOURCES:
        assert isinstance(src.name, str) and src.name
        assert isinstance(src.filename, str) and src.filename


def test_extra_source_classes_are_independently_usable(tmp_path: Path):
    """Sanity: bypass the registry and use a class directly."""
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text('[tool.multicz.project]\ncommit_convention = "conventional"\n')
    raw = PyprojectSource().extract(pyproj)
    assert raw is not None and raw["project"]["commit_convention"] == "conventional"

    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"multicz": {"project": {"commit_convention": "conventional"}}}))
    raw = PackageJsonSource().extract(pkg)
    assert raw is not None and raw["project"]["commit_convention"] == "conventional"
