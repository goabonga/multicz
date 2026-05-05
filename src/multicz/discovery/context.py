# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cross-strategy state for ``multicz init``'s component discovery.

A discovery strategy (see :mod:`.python`, :mod:`.helm`, etc.) walks one
ecosystem's manifests and emits :class:`DiscoveryResult` objects. The
orchestrator in ``__init__`` is responsible for *naming* (collision
resolution against everything already discovered) and for running the
post-pass relations (e.g. wiring a Python component's ``mirrors`` into
the matching Helm chart's ``appVersion``). Both responsibilities need
shared state; that state lives here.

The previous implementation kept everything as locals inside
``discover_components()``. Moving them onto a dataclass makes the
contract explicit and lets each strategy take a single ``context``
parameter instead of growing a long argument list as we add more
ecosystem types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..config import Component

DiscoveryKind = Literal[
    "python",
    "cargo",
    "gradle",
    "go",
    "helm",
    "node",
    "debian",
]


@dataclass(frozen=True)
class DiscoveryResult:
    """A single component candidate produced by a discovery strategy.

    ``raw_name`` is the manifest-declared name (``[project].name`` from
    ``pyproject.toml``, ``name`` from ``Chart.yaml``, ``"name"`` from
    ``package.json``, ...). The orchestrator may rename the resulting
    component if ``raw_name`` collides with another already-discovered
    component — ``suffix`` is the disambiguator candidate it appends
    on collision (``"py"`` for Python, ``"chart"`` for Helm, etc.).

    ``component`` carries the actual `Component` model (paths,
    bump_files, changelog, ...) the strategy built. The orchestrator
    inserts it into the final dict under the resolved name.
    """

    raw_name: str
    kind: DiscoveryKind
    suffix: str
    component: Component


@dataclass
class DiscoveryContext:
    """Mutable state threaded through every strategy and relation.

    * ``repo`` — the workspace root every relative path resolves
      against.
    * ``taken_names`` — the set of component names already claimed,
      used by :meth:`unique` to disambiguate collisions.
    * ``results`` — every emitted :class:`DiscoveryResult`, in
      insertion order, decorated with the *resolved* component name.
      Relations consume this to find peers across strategies (e.g.
      "every Python component" + "every Helm chart" → mirror wiring).
    """

    repo: Path
    taken_names: set[str] = field(default_factory=set)
    results: list[tuple[str, DiscoveryResult]] = field(default_factory=list)

    def unique(self, raw_name: str, suffix: str) -> str:
        """Resolve ``raw_name`` to a name not yet claimed in this run.

        Returns ``raw_name`` directly when free, otherwise appends
        ``-<suffix>`` (then ``-<suffix>-2``, ``-<suffix>-3``, ...) until
        a free slot is found. The returned name is registered as
        taken.
        """
        if raw_name not in self.taken_names:
            self.taken_names.add(raw_name)
            return raw_name
        candidate = f"{raw_name}-{suffix}"
        counter = 2
        while candidate in self.taken_names:
            candidate = f"{raw_name}-{suffix}-{counter}"
            counter += 1
        self.taken_names.add(candidate)
        return candidate

    def register(self, name: str, result: DiscoveryResult) -> None:
        """Record a resolved (name, result) pair for relations to query."""
        self.results.append((name, result))

    def by_kind(self, kind: DiscoveryKind) -> list[tuple[str, DiscoveryResult]]:
        """Filter ``results`` by strategy kind. Used by relations."""
        return [(n, r) for n, r in self.results if r.kind == kind]

    def components(self) -> dict[str, Component]:
        """Materialize the discovery output as a name -> Component map."""
        return {name: result.component for name, result in self.results}
