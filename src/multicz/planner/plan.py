# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Pure-data and pure-function helpers for version transitions.

This module contains the primitives the planner uses to decide *what*
the next version of a component looks like, without touching git or
config: the bump kind ordering, version arithmetic, pre-release
rendering, and the :class:`Plan` / :class:`PlannedBump` containers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from packaging.version import Version

from ..commits import BumpKind
from .reasons import Reason

_KIND_ORDER: dict[BumpKind, int] = {"patch": 1, "minor": 2, "major": 3}


def _stronger(a: BumpKind | None, b: BumpKind | None) -> BumpKind | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if _KIND_ORDER[a] >= _KIND_ORDER[b] else b


def aggregate_kind(kinds: Iterable[BumpKind | None]) -> BumpKind | None:
    result: BumpKind | None = None
    for kind in kinds:
        result = _stronger(result, kind)
    return result


def bump_version(version: Version, kind: BumpKind) -> Version:
    major, minor, patch = version.major, version.minor, version.micro
    if kind == "major":
        return Version(f"{major + 1}.0.0")
    if kind == "minor":
        return Version(f"{major}.{minor + 1}.0")
    return Version(f"{major}.{minor}.{patch + 1}")


# PEP 440 normalises 'a'/'b'/'c' into 'alpha'/'beta'/'rc' shapes; we keep a
# dictionary of common aliases so 1.3.0-rc.1 and 1.3.0-c.1 collapse to the
# same cycle.
_PRE_ALIASES = {"a": "alpha", "b": "beta", "c": "rc", "pre": "rc", "preview": "rc"}


def _norm_pre_label(label: str) -> str:
    label = label.lower()
    return _PRE_ALIASES.get(label, label)


VersionScheme = Literal["semver", "pep440"]

# PEP 440 canonical labels: 'a' / 'b' / 'rc'. We accept both compact and
# spelled-out forms on input; output uses canonical compact labels for
# the pep440 scheme.
_PEP440_COMPACT = {"alpha": "a", "beta": "b", "c": "rc", "pre": "rc", "preview": "rc"}


def _render_pre(
    base: str, label: str, num: int, scheme: VersionScheme
) -> str:
    """Render ``base + pre-release suffix`` in the requested scheme."""
    if scheme == "pep440":
        compact = _PEP440_COMPACT.get(label.lower(), label.lower())
        return f"{base}{compact}{num}"
    # semver default
    return f"{base}-{label}.{num}"


def compute_next(
    current: Version,
    kind: BumpKind,
    *,
    pre: str | None = None,
    finalize: bool = False,
    scheme: VersionScheme = "semver",
) -> str:
    """Compute the next version string given ``kind`` and optional pre-release flags.

    Output is rendered in the chosen ``scheme``:

    * ``semver`` (default): ``1.3.0-rc.1`` - npm, Cargo, Helm, generic
    * ``pep440``: ``1.3.0rc1`` - strict canonical Python form

    Either form can be re-parsed by :class:`packaging.version.Version` so
    ordering is preserved across both. The behavior matrix below uses
    semver rendering for readability.

    +-------------+----------+-----------+------------------+----------------------+
    | current     | --pre    | --finalize| result (semver)  | meaning              |
    +-------------+----------+-----------+------------------+----------------------+
    | 1.2.3       | None     | False     | 1.3.0            | regular bump (feat)  |
    | 1.2.3       | rc       | False     | 1.3.0-rc.1       | enter RC cycle       |
    | 1.3.0-rc.1  | None     | False     | 1.3.0            | auto-finalize        |
    | 1.3.0-rc.1  | None     | True      | 1.3.0            | explicit finalize    |
    | 1.3.0-rc.1  | rc       | False     | 1.3.0-rc.2       | next RC              |
    | 1.3.0-rc.1  | beta     | False     | 1.3.0-beta.1     | switch label         |
    +-------------+----------+-----------+------------------+----------------------+
    """
    base = f"{current.major}.{current.minor}.{current.micro}"

    if finalize:
        if current.is_prerelease:
            return base
        bumped = bump_version(current, kind)
        return f"{bumped.major}.{bumped.minor}.{bumped.micro}"

    if pre is None:
        if current.is_prerelease:
            return base
        bumped = bump_version(current, kind)
        return f"{bumped.major}.{bumped.minor}.{bumped.micro}"

    # pre is set: entering or continuing a pre-release cycle
    if current.is_prerelease and current.pre is not None:
        existing = _norm_pre_label(current.pre[0])
        wanted = _norm_pre_label(pre)
        if existing == wanted:
            counter = (current.pre[1] or 0) + 1
            return _render_pre(base, pre, counter, scheme)
        # Different label, same target version
        return _render_pre(base, pre, 1, scheme)

    # Currently a final release: bump first, then enter the pre cycle
    target = bump_version(current, kind)
    target_base = f"{target.major}.{target.minor}.{target.micro}"
    return _render_pre(target_base, pre, 1, scheme)


@dataclass
class PlannedBump:
    component: str
    current: Version
    kind: BumpKind
    reasons: list[Reason] = field(default_factory=list)
    pre: str | None = None
    finalize: bool = False
    scheme: VersionScheme = "semver"

    @property
    def next(self) -> str:
        """The new version, rendered in this component's :attr:`scheme`."""
        return compute_next(
            self.current,
            self.kind,
            pre=self.pre,
            finalize=self.finalize,
            scheme=self.scheme,
        )

    @property
    def next_version(self) -> Version:
        """Parsed Version of :attr:`next` (for ordering)."""
        return Version(self.next)

    def reason_summaries(self) -> list[str]:
        return [r.summary() for r in self.reasons]


@dataclass
class Plan:
    bumps: dict[str, PlannedBump] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.bumps)

    def __iter__(self):
        return iter(self.bumps.values())
