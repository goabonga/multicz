# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Planner package: split into reasons, plan, and build submodules.

The full public surface is re-exported here for backward compatibility
with callers that import ``multicz.planner.<symbol>`` directly.
"""

from .build import _current_version as _current_version
from .build import build_plan
from .plan import (
    Plan,
    PlannedBump,
    aggregate_kind,
    bump_version,
    compute_next,
)
from .reasons import (
    CommitReason,
    ManualReason,
    MirrorReason,
    NonConventionalCommitsError,
    NonConventionalReason,
    TriggerReason,
)

__all__ = [
    "CommitReason",
    "ManualReason",
    "MirrorReason",
    "NonConventionalCommitsError",
    "NonConventionalReason",
    "Plan",
    "PlannedBump",
    "TriggerReason",
    "aggregate_kind",
    "build_plan",
    "bump_version",
    "compute_next",
]
