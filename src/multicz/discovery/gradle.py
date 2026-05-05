# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Gradle ecosystem discovery (root ``gradle.properties``)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from ..config import Component, FileKey
from .context import DiscoveryContext, DiscoveryResult

_GRADLE_NAME_RE = re.compile(
    r"rootProject\.name\s*=\s*['\"]([^'\"]+)['\"]"
)


def _read_gradle_property(path: Path, key: str) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped[0] in "#!":
            continue
        if "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        if k.strip() == key:
            return v.strip()
    return None


def _read_gradle_root_name(repo: Path) -> str | None:
    for filename in ("settings.gradle", "settings.gradle.kts"):
        path = repo / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        match = _GRADLE_NAME_RE.search(text)
        if match:
            return match.group(1)
    return None


class GradleDiscovery:
    """Discover a Gradle project from a root ``gradle.properties`` file."""

    name = "gradle"

    def discover(
        self, repo: Path, context: DiscoveryContext
    ) -> Iterable[DiscoveryResult]:
        properties_path = repo / "gradle.properties"
        if not properties_path.is_file():
            return
        version = _read_gradle_property(properties_path, "version")
        if version is None:
            return
        raw_name = _read_gradle_root_name(repo) or repo.name
        paths = ["gradle.properties"]
        if (repo / "src").is_dir():
            paths.insert(0, "src/**")
        for fn in (
            "build.gradle",
            "build.gradle.kts",
            "settings.gradle",
            "settings.gradle.kts",
        ):
            if (repo / fn).is_file():
                paths.append(fn)
        if (repo / "Dockerfile").is_file():
            paths.append("Dockerfile")
        component = Component(
            paths=paths,
            bump_files=[FileKey(file=Path("gradle.properties"), key="version")],
            changelog=Path("CHANGELOG.md"),
        )
        yield DiscoveryResult(
            raw_name=raw_name,
            kind="gradle",
            suffix="gradle",
            component=component,
        )
