# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Reason dataclasses describing why a component is in the plan.

Each reason is a frozen dataclass that records the cause of a planned
bump (a commit, a trigger from an upstream component, a mirror cascade,
a manual CLI flag, or a non-conventional commit). The
:class:`NonConventionalCommitsError` is raised by the planner when the
``unknown_commit_policy = "error"`` mode encounters offending commits.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..commits import BumpKind


@dataclass(frozen=True)
class CommitReason:
    """A planned bump driven by a conventional commit landing on this component."""

    sha: str
    type: str
    scope: str | None
    breaking: bool
    subject: str
    files: tuple[str, ...]  # files matched into THIS component (subset of commit.files)
    bump_kind: BumpKind
    # When ``bump_policy = "scoped"`` demotes this commit's natural kind
    # (e.g. minor -> patch because the scope points at another component),
    # ``original_kind`` records what would have been used otherwise.
    # ``None`` means no demotion happened.
    original_kind: BumpKind | None = None

    def summary(self) -> str:
        bang = "!" if self.breaking else ""
        scope = f"({self.scope})" if self.scope else ""
        head = f"{self.sha[:7]} {self.type}{scope}{bang}: {self.subject}"
        if self.original_kind is not None:
            head += f" [demoted: {self.original_kind} -> {self.bump_kind}]"
        return head

    def to_dict(self) -> dict:
        return {
            "kind": "commit",
            "sha": self.sha,
            "type": self.type,
            "scope": self.scope,
            "breaking": self.breaking,
            "subject": self.subject,
            "files": list(self.files),
            "bump_kind": self.bump_kind,
            "original_kind": self.original_kind,
        }


@dataclass(frozen=True)
class TriggerReason:
    """A planned bump cascaded from a declared upstream component."""

    upstream: str
    upstream_kind: BumpKind

    def summary(self) -> str:
        return f"triggered by {self.upstream} ({self.upstream_kind})"

    def to_dict(self) -> dict:
        return {
            "kind": "trigger",
            "upstream": self.upstream,
            "upstream_kind": self.upstream_kind,
        }


@dataclass(frozen=True)
class MirrorReason:
    """A planned bump cascaded from a mirror writing into this component's path."""

    upstream: str
    file: str
    key: str | None

    def summary(self) -> str:
        target = self.file if self.key is None else f"{self.file}:{self.key}"
        return f"mirror cascade from {self.upstream} ({target})"

    def to_dict(self) -> dict:
        return {
            "kind": "mirror",
            "upstream": self.upstream,
            "file": self.file,
            "key": self.key,
        }


@dataclass(frozen=True)
class ManualReason:
    """A planned bump that came from a CLI flag (``--finalize``, force-bump,
    …) rather than a commit, trigger, or mirror."""

    note: str

    def summary(self) -> str:
        return self.note

    def to_dict(self) -> dict:
        return {"kind": "manual", "note": self.note}


@dataclass(frozen=True)
class NonConventionalReason:
    """A planned bump driven by a commit that did NOT match the conventional
    commit grammar. Only produced when
    ``project.unknown_commit_policy = "patch"``.
    """

    sha: str
    subject: str  # the commit's first line, verbatim
    files: tuple[str, ...]
    bump_kind: BumpKind = "patch"

    def summary(self) -> str:
        return f"{self.sha[:7]} (non-conventional): {self.subject}"

    def to_dict(self) -> dict:
        return {
            "kind": "non_conventional",
            "sha": self.sha,
            "subject": self.subject,
            "files": list(self.files),
            "bump_kind": self.bump_kind,
        }


Reason = (
    CommitReason | TriggerReason | MirrorReason | ManualReason | NonConventionalReason
)


class NonConventionalCommitsError(RuntimeError):
    """Raised when ``unknown_commit_policy = "error"`` and the planner
    encountered at least one non-conventional commit in scope.
    """

    def __init__(self, offenders: list[tuple[str, str]]) -> None:
        # offenders: list of (sha, first_line)
        self.offenders = offenders
        super().__init__(
            f"{len(offenders)} non-conventional commit(s) blocking the plan"
        )
