# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover Gradle discovery error handling and optional paths."""

from pathlib import Path

from multicz.discovery.context import DiscoveryContext
from multicz.discovery.gradle import (
    GradleDiscovery,
    _read_gradle_property,
    _read_gradle_root_name,
)


def test_property_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "gradle.properties"
    path.write_bytes(b"\xff\xfe\x00")
    assert _read_gradle_property(path, "version") is None


def test_property_skips_lines_without_equals(tmp_path: Path) -> None:
    path = tmp_path / "gradle.properties"
    path.write_text("# comment\n\njust text\nversion = 1.2.3\n")
    assert _read_gradle_property(path, "version") == "1.2.3"


def test_root_name_skips_unreadable_settings(tmp_path: Path) -> None:
    (tmp_path / "settings.gradle").write_bytes(b"\xff\xfe\x00")
    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "kts"\n')
    assert _read_gradle_root_name(tmp_path) == "kts"


def test_discover_adds_src_dockerfile_and_build_files(tmp_path: Path) -> None:
    (tmp_path / "gradle.properties").write_text("version=1.0.0\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "Dockerfile").write_text("")
    (tmp_path / "build.gradle").write_text("")
    results = list(GradleDiscovery().discover(tmp_path, DiscoveryContext(repo=tmp_path)))
    assert results[0].component.paths == [
        "src/**",
        "gradle.properties",
        "build.gradle",
        "Dockerfile",
    ]
