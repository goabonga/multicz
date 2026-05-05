# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Helm ecosystem discovery (``Chart.yaml``)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ruamel.yaml import YAML

from ..config import Component, FileKey
from ._common import _find_manifests
from .context import DiscoveryContext, DiscoveryResult


def _read_chart_name(path: Path) -> str | None:
    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    name = data.get("name")
    return str(name) if name else None


def _find_chart_yamls(repo: Path) -> list[Path]:
    return _find_manifests(repo, "Chart.yaml")


class HelmDiscovery:
    """Discover Helm charts from every ``Chart.yaml`` under the repo."""

    name = "helm"

    def discover(
        self, repo: Path, context: DiscoveryContext
    ) -> Iterable[DiscoveryResult]:
        for chart_yaml in _find_chart_yamls(repo):
            chart_dir = chart_yaml.parent
            rel_dir = chart_dir.relative_to(repo).as_posix()
            rel_chart = chart_yaml.relative_to(repo)
            raw = _read_chart_name(chart_yaml) or chart_dir.name
            component = Component(
                paths=[f"{rel_dir}/**"],
                bump_files=[FileKey(file=rel_chart, key="version")],
                changelog=Path(f"{rel_dir}/CHANGELOG.md"),
            )
            yield DiscoveryResult(
                raw_name=raw,
                kind="helm",
                suffix="chart",
                component=component,
            )
