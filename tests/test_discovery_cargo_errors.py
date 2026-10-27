# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover Cargo discovery error handling and optional root paths."""

from pathlib import Path

from multicz.discovery.cargo import CargoDiscovery, _read_cargo, _read_cargo_excludes
from multicz.discovery.context import DiscoveryContext


def test_excludes_ignores_unparseable_root(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("not [valid toml")
    assert _read_cargo_excludes(tmp_path) == set()


def test_excludes_ignores_non_string_entries(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[workspace]\nexclude = [1, 'gone']\n")
    assert _read_cargo_excludes(tmp_path) == set()


def test_read_cargo_unparseable(tmp_path: Path) -> None:
    path = tmp_path / "Cargo.toml"
    path.write_text("not [valid toml")
    assert _read_cargo(path) is None


def test_read_cargo_workspace_root_with_package_name(tmp_path: Path) -> None:
    path = tmp_path / "Cargo.toml"
    path.write_text(
        '[workspace.package]\nversion = "1.0.0"\n'
        '[package]\nname = "root"\nversion.workspace = true\n'
    )
    assert _read_cargo(path) == ("root", "workspace.package.version")


def test_read_cargo_package_without_name(tmp_path: Path) -> None:
    path = tmp_path / "Cargo.toml"
    path.write_text('[package]\nversion = "1.0.0"\n')
    assert _read_cargo(path) is None


def test_root_paths_include_lock_tests_and_dockerfile(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "c"\nversion = "1.0.0"\n')
    (tmp_path / "Cargo.lock").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "Dockerfile").write_text("")
    results = list(CargoDiscovery().discover(tmp_path, DiscoveryContext(repo=tmp_path)))
    assert results[0].component.paths == [
        "src/**",
        "Cargo.toml",
        "Cargo.lock",
        "tests/**",
        "Dockerfile",
    ]


def test_workspace_only_manifest_without_name_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[workspace.package]\nversion = "1.0.0"\n')
    assert list(CargoDiscovery().discover(tmp_path, DiscoveryContext(repo=tmp_path))) == []
