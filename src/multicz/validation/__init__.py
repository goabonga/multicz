# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Configuration and repository sanity checks for multicz.

The :func:`validate` function runs every check in :data:`CHECKS` and
returns a flat list of :class:`Finding`s. Each finding has a level
(``error``, ``warning``, ``info``), a stable ``check`` identifier, an
optional component name, and a human-readable message. The CLI
``multicz validate`` command exits non-zero when any error is reported
(and when ``--strict`` is passed, also when any warning is).

Each check is a small class implementing :class:`Check`; the registry
below preserves the historical execution order. Adding a new check is
one new module + one entry in :data:`CHECKS`.
"""

from __future__ import annotations

from pathlib import Path

from ..config import ComponentMatcher, Config
from ._base import Check, Finding, Level, ValidationContext
from .bump_files import BumpFilesExistCheck
from .changelog import ChangelogPathCheck, DebianChangelogCheck
from .cycles import MirrorCycleCheck, TriggerCycleCheck
from .mirrors import MirrorTargetsCheck
from .overlap import PathOverlapCheck
from .state import StateDriftCheck
from .versions import CurrentVersionCheck

CHECKS: list[Check] = [
    BumpFilesExistCheck(),
    PathOverlapCheck(),
    MirrorTargetsCheck(),
    TriggerCycleCheck(),
    MirrorCycleCheck(),
    ChangelogPathCheck(),
    CurrentVersionCheck(),
    DebianChangelogCheck(),
    StateDriftCheck(),
]
# Order matches the original validate() ordering — preserve it.


def validate(repo: Path, config: Config) -> list[Finding]:
    """Run every sanity check and return a flat list of findings."""
    matcher = ComponentMatcher(config.components)
    ctx = ValidationContext(repo=repo, config=config, matcher=matcher)
    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check.run(ctx))
    return findings


__all__ = [
    "CHECKS",
    "BumpFilesExistCheck",
    "ChangelogPathCheck",
    "Check",
    "CurrentVersionCheck",
    "DebianChangelogCheck",
    "Finding",
    "Level",
    "MirrorCycleCheck",
    "MirrorTargetsCheck",
    "PathOverlapCheck",
    "StateDriftCheck",
    "TriggerCycleCheck",
    "ValidationContext",
    "validate",
]
