# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover ``skip`` filtering and the optional sections of ``render_config``."""

from pathlib import Path

import tomlkit

from multicz.config import Component, DebianChangelogWriter, FileKey
from multicz.discovery import discover_components, render_config


def test_discover_components_skips_named_strategy(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "app"\nversion = "1.0.0"\n')
    assert "app" in discover_components(tmp_path)
    assert discover_components(tmp_path, skip={"python"}) == {}


def test_render_config_emits_every_optional_section() -> None:
    comp = Component(
        paths=["src/**"],
        exclude_paths=["src/gen/**"],
        bump_files=[FileKey(file=Path("a.toml"), key="v")],
        depends_on=["other"],
        changelog=Path("CHANGELOG.md"),
        writers=[
            DebianChangelogWriter(
                type="debian-changelog",
                distribution="stable",
                urgency="high",
                debian_revision=3,
                maintainer="Me <me@example.com>",
                epoch=2,
            )
        ],
    )
    text = render_config({"app": comp})
    section = tomlkit.parse(text)["components"]["app"]
    assert section["exclude_paths"] == ["src/gen/**"]
    assert section["depends_on"] == ["other"]
    assert section["changelog"] == "CHANGELOG.md"
    writer = section["writers"][0]
    assert writer["distribution"] == "stable"
    assert writer["urgency"] == "high"
    assert writer["debian_revision"] == 3
    assert writer["maintainer"] == "Me <me@example.com>"
    assert writer["epoch"] == 2


def test_render_config_omits_default_writer_fields() -> None:
    comp = Component(
        paths=["debian/**"],
        writers=[DebianChangelogWriter(type="debian-changelog")],
    )
    writer = tomlkit.parse(render_config({"pkg": comp}))["components"]["pkg"]["writers"][0]
    assert set(writer) == {"type", "file"}
