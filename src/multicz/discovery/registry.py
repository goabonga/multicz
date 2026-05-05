# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Static registry of discovery strategies.

Strategies listed here are run by :func:`multicz.discovery.discover_components`
in order. The order matters for collision-resolution: the first strategy
to claim a ``raw_name`` keeps it; later strategies disambiguate by
appending their suffix. Today the order mirrors the pre-refactor
implementation (Python first, then Cargo, Gradle, Go, Helm).

Cross-ecosystem concerns (Python <-> Helm appVersion mirroring, the
Node workspace post-pass, Debian detection) are not strategies yet —
they run after the registry loop. Stage 4 will introduce a
``RelationStrategy`` protocol for them.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from .cargo import CargoDiscovery
from .context import DiscoveryContext, DiscoveryResult
from .go import GoDiscovery
from .gradle import GradleDiscovery
from .helm import HelmDiscovery
from .python import PythonDiscovery


class DiscoveryStrategy(Protocol):
    name: str

    def discover(
        self, repo: Path, context: DiscoveryContext
    ) -> Iterable[DiscoveryResult]: ...


DISCOVERERS: list[DiscoveryStrategy] = [
    PythonDiscovery(),
    CargoDiscovery(),
    GradleDiscovery(),
    GoDiscovery(),
    HelmDiscovery(),
]
