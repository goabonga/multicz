# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Core protocol every validation check implements.

multicz runs a fixed list of sanity checks against a repo + parsed
config and produces a flat list of :class:`Finding`s. Every check is a
small class implementing :class:`Check`; checks are stateless,
constructed once at module load time, and listed in the registry in
:mod:`multicz.validation`. Each check sees the same
:class:`ValidationContext` so the matcher is built once.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from ..config import ComponentMatcher, Config

Level = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Finding:
    level: Level
    check: str
    component: str | None
    message: str

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "check": self.check,
            "component": self.component,
            "message": self.message,
        }


@dataclass(frozen=True)
class ValidationContext:
    """Inputs every check sees.

    Carries a precomputed :class:`ComponentMatcher` so checks that
    need it don't each rebuild one.
    """

    repo: Path
    config: Config
    matcher: ComponentMatcher


class Check(Protocol):
    """Run a single sanity check against the validation context.

    Implementations are stateless — instances are created once at
    module load time and reused. ``name`` identifies the check in the
    registry; the ``check`` field on each yielded :class:`Finding` is
    a finer-grained identifier and may differ from ``name`` when one
    check produces several finding kinds.
    """

    name: str

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        """Yield findings for this check."""
        ...
