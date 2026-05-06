# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cross-strategy relations applied after every discovery has run.

A :class:`RelationStrategy` reads the discovered components and patches
them in place. Examples shipped today:

* :class:`PythonHelmAppVersionRelation` - when a Python component lives
  next to a Helm chart, mirror the Python version into the chart's
  ``appVersion``. The mirror is unambiguous when there's exactly one
  Python and one chart; otherwise it pairs by manifest-declared name.
* :class:`NodeWorkspaceRelation` - expand a root ``package.json`` with
  ``workspaces`` declarations (or a sibling ``pnpm-workspace.yaml``) into
  one component per workspace member, deferring to the existing
  :func:`.node._detect_node` post-pass since it already needs the
  resolved Python set to decide whether to claim the root CHANGELOG.

Adding a new cross-ecosystem link is a matter of writing a new strategy
and appending it to :data:`RELATIONS`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from ..config import Component, FileKey
from .context import DiscoveryContext
from .debian import _detect_debian
from .node import _detect_node


class RelationStrategy(Protocol):
    """Post-discovery patch applied to the component map.

    Mutates ``components`` in place; ``context`` is read-only at this
    stage (every strategy has already run). Implementations are expected
    to be idempotent — calling twice should produce the same final
    state — so the orchestrator can replay them in tests.
    """

    name: str

    def link(
        self,
        repo: Path,
        components: dict[str, Component],
        context: DiscoveryContext,
    ) -> None: ...


class PythonHelmAppVersionRelation:
    """Mirror a Python component's version into the matching chart's ``appVersion``."""

    name = "python-helm-appversion"

    def link(
        self,
        repo: Path,
        components: dict[str, Component],
        context: DiscoveryContext,
    ) -> None:
        pythons = context.by_kind("python")
        charts = context.by_kind("helm")
        if not pythons or not charts:
            return

        if len(pythons) == 1 and len(charts) == 1:
            py_name, _ = pythons[0]
            chart_name, _ = charts[0]
            chart_yaml_path = components[chart_name].bump_files[0].file
            components[py_name].mirrors.append(
                FileKey(file=chart_yaml_path, key="appVersion")
            )
            return

        for py_name, py_result in pythons:
            py = components[py_name]
            for chart_comp_name, chart_result in charts:
                if chart_result.raw_name == py_result.raw_name:
                    chart_yaml_path = components[chart_comp_name].bump_files[0].file
                    py.mirrors.append(
                        FileKey(file=chart_yaml_path, key="appVersion")
                    )


class NodeWorkspaceRelation:
    """Expand root package.json + workspaces into one component per member.

    Defers to :func:`.node._detect_node` since that helper already
    handles the python-rooted-changelog interplay. A future refactor
    could fold ``_detect_node`` directly into this class once the Node
    discovery becomes a regular strategy.
    """

    name = "node-workspaces"

    def link(
        self,
        repo: Path,
        components: dict[str, Component],
        context: DiscoveryContext,
    ) -> None:
        _detect_node(repo, components, context)


class DebianChangelogRelation:
    """Detect a top-level ``debian/changelog`` and add a component with
    a ``debian-changelog`` writer.

    Currently a thin wrapper over :func:`.debian._detect_debian`; the
    Protocol surface lets a future writer-aware project policy swap it
    out (e.g. detect package-per-binary in a multi-binary
    debian/control).
    """

    name = "debian-changelog"

    def link(
        self,
        repo: Path,
        components: dict[str, Component],
        context: DiscoveryContext,
    ) -> None:
        _detect_debian(repo, components)


RELATIONS: list[RelationStrategy] = [
    PythonHelmAppVersionRelation(),
    NodeWorkspaceRelation(),
    DebianChangelogRelation(),
]


def apply_relations(
    repo: Path,
    components: dict[str, Component],
    context: DiscoveryContext,
    *,
    relations: Iterable[RelationStrategy] | None = None,
) -> None:
    """Run every relation in :data:`RELATIONS` (or a custom set) over ``components``."""
    for relation in relations if relations is not None else RELATIONS:
        relation.link(repo, components, context)
