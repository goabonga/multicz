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
from dataclasses import dataclass
from typing import Literal

BumpKind = Literal["major", "minor", "patch"]

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
        """Semver level implied by the conventional-commit type.

        ``major``: ``!`` marker or ``BREAKING CHANGE:`` footer.
        ``minor``: ``feat``.
        ``patch``: ``fix``, ``perf``, ``revert``. A revert is a
        user-visible change (something was removed or restored), and a
        patch is the conservative answer - the next release isn't a
        feature or breaking change, but it isn't nothing either.

        Other types (``chore``, ``docs``, ``style``, ``refactor``,
        ``test``, ``build``, ``ci``) return ``None`` and don't bump.
        """
        if self.breaking:
            return "major"
        if self.type.lower() == "feat":
            return "minor"
        if self.type.lower() in {"fix", "perf", "revert"}:
            return "patch"
        return None


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
