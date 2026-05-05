# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Typed value objects passed between command compute paths and presenters.

Each dataclass replaces a ``dict[str, Any]`` blob or a multi-positional
function signature that grew during the stage-2 presenters extraction.
Frozen + slots-equivalent (``frozen=True``) for predictability: the
compute side fills these once, the presenter reads them.

These types live in ``cli/`` only - they're not part of any public API
and are deliberately decoupled from ``planner`` / ``changelog`` /
``state`` value objects (which already exist and stay where they are).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..changelog import CascadeEntry
from ..commits import Commit
from ..validation import Finding

# ============ bump ============


@dataclass(frozen=True)
class AppliedBump:
    """One component's applied bump in a ``multicz bump`` run.

    Mirrors the per-component dict the legacy code stored under
    ``applied[name] = {"current": ..., "next": ..., "kind": ...}``.
    """

    component: str
    current: str
    next: str
    kind: str


@dataclass(frozen=True)
class GitSummary:
    """Git side-effects of a bump (commit SHA, tags, push, signing).

    Replaces the ad-hoc ``git_summary: dict[str, str | list[str]]`` dict.
    Empty defaults mean "this side-effect didn't happen" (no commit, no
    tags, not pushed); presenters check ``commit_sha`` truthiness etc.
    rather than ``"commit" in dict``.
    """

    commit_sha: str | None = None
    tags: tuple[str, ...] = ()
    pushed: bool = False
    signed_commit: bool = False
    signed_tags: bool = False


@dataclass(frozen=True)
class BumpResult:
    """Full result of a ``multicz bump`` invocation."""

    bumps: tuple[AppliedBump, ...]
    dry_run: bool
    git: GitSummary
    changelogs: tuple[str, ...]


# ============ release-notes ============


@dataclass(frozen=True)
class ReleaseNotesSection:
    """One component's section in a ``multicz release-notes`` run.

    Replaces the per-section dict carried through ``sections: list[dict]``.
    ``cascades`` is empty for the ``--tag`` retrospective mode (no plan
    reasons exist).
    """

    component: str
    from_version: str | None
    to_version: str
    commits: tuple[Commit, ...]
    cascades: tuple[CascadeEntry, ...] = ()


# ============ validate ============


@dataclass(frozen=True)
class ValidationReport:
    """Findings of a ``multicz validate`` run, pre-bucketed by level.

    The presenter formerly took ``findings, errors, warnings, infos``
    as four separate args. Bucketing happens once on the compute side.
    """

    findings: tuple[Finding, ...]
    errors: tuple[Finding, ...]
    warnings: tuple[Finding, ...]
    infos: tuple[Finding, ...]


# ============ changelog ============


@dataclass(frozen=True)
class ChangelogEntry:
    """One per-component entry in a ``multicz changelog`` run.

    ``planned`` is the planner's ``PlannedBump`` (or ``None`` when no
    bump is pending). Typed as ``object`` to avoid a planner import here.
    """

    component: str
    since: str | None
    relevant: tuple[Commit, ...]
    planned: object | None = None


# ============ changed ============


@dataclass(frozen=True)
class ChangedReport:
    """Result of a ``multicz changed`` run."""

    changed: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
