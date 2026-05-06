# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Conventional Commit parsing primitives.

Pure string manipulation: regexes, the :class:`Commit` dataclass, the
allowed-type vocabulary, message validation, and the :func:`parse_commit`
function that turns a raw commit message into a structured record. No I/O
happens in this module.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

BumpKind = Literal["major", "minor", "patch"]
BumpRule = Literal["major", "minor", "patch", "none"]

_HEADER_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?"
    r": (?P<subject>.+)$"
)
_BREAKING_FOOTER_RE = re.compile(r"^BREAKING(?:[ -]CHANGE)?:", re.MULTILINE)

DEFAULT_TYPES: tuple[str, ...] = (
    "feat", "fix", "perf", "refactor", "docs", "test",
    "build", "ci", "chore", "style", "revert",
)
DEFAULT_BUMP_RULES: dict[str, BumpRule] = {
    "feat": "minor",
    "fix": "patch",
    "perf": "patch",
    "revert": "patch",
}
_AUTO_PREFIXES: tuple[str, ...] = (
    "Merge ", "Revert ", "fixup!", "squash!", "amend!",
)


def validate_message(message: str, allowed_types: tuple[str, ...] = DEFAULT_TYPES) -> str | None:
    """Return a human-readable error if ``message`` is not a valid conventional commit.

    Lines that git tooling generates automatically (Merge/Revert/fixup!/squash!/amend!)
    are accepted unconditionally. ``None`` means the message is valid.
    """
    stripped = message.lstrip("﻿").strip()
    if not stripped:
        return "empty commit message"

    first = stripped.splitlines()[0]
    if first.startswith(_AUTO_PREFIXES):
        return None

    match = _HEADER_RE.match(first)
    if match is None:
        return (
            "header does not match '<type>(<scope>)?: <subject>'. "
            f"Allowed types: {', '.join(allowed_types)}."
        )
    if match.group("type").lower() not in allowed_types:
        return (
            f"unknown type {match.group('type')!r}. "
            f"Allowed types: {', '.join(allowed_types)}."
        )
    return None


@dataclass(frozen=True)
class Commit:
    sha: str
    type: str
    scope: str | None
    breaking: bool
    subject: str
    body: str
    files: tuple[str, ...]

    @property
    def is_conventional(self) -> bool:
        return self.type != ""

    @property
    def bump_kind(self) -> BumpKind | None:
        """Semver level under :data:`DEFAULT_BUMP_RULES`.

        Convenience for callers that don't have a :class:`Config` in
        scope. The planner uses :func:`bump_kind_for` with the
        component-effective ``bump_rules`` instead.
        """
        return bump_kind_for(self, DEFAULT_BUMP_RULES)


def bump_kind_for(commit: Commit, rules: Mapping[str, BumpRule]) -> BumpKind | None:
    """Resolve the semver level for ``commit`` under ``rules``.

    Resolution order:

    1. Type explicitly mapped to ``"none"`` -> always skip, even when
       the commit is breaking. Mirrors the legacy ``ignored_types``
       opt-out: silencing a type silences its breaking variants too.
    2. Otherwise breaking commits (``!`` marker or ``BREAKING CHANGE:``
       footer) bump major.
    3. Otherwise the rule's value (``major`` / ``minor`` / ``patch``).
    4. Type absent from ``rules`` and not breaking -> no bump.
    """
    rule = rules.get(commit.type.lower())
    if rule == "none":
        return None
    if commit.breaking:
        return "major"
    if rule is None:
        return None
    return rule


def parse_commit(sha: str, message: str, files: tuple[str, ...]) -> Commit:
    """Parse a raw commit message into a structured :class:`Commit`."""
    lines = message.splitlines()
    header = lines[0] if lines else ""
    body = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""

    match = _HEADER_RE.match(header)
    if match is None:
        return Commit(sha=sha, type="", scope=None, breaking=False,
                      subject=header, body=body, files=files)

    breaking = bool(match.group("breaking")) or bool(_BREAKING_FOOTER_RE.search(body))
    return Commit(
        sha=sha,
        type=match.group("type"),
        scope=match.group("scope"),
        breaking=breaking,
        subject=match.group("subject"),
        body=body,
        files=files,
    )


def tag_prefix(tag_format: str, component: str) -> str:
    """Render the prefix used to look up tags for ``component``.

    Given ``"{component}-v{version}"`` and ``"api"`` returns ``"api-v"``.
    """
    rendered = tag_format.format(component=component, version="\0VERSION\0")
    head, _, _ = rendered.partition("\0VERSION\0")
    return head
