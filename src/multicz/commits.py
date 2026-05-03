# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Conventional Commit parsing over a git history range.

Resolves the latest tag matching a component's tag prefix, lists the commits
since that tag (or the entire history if no tag exists), and parses each
commit header into a :class:`Commit` with the implied semver bump kind.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from packaging.version import InvalidVersion, Version

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


class GitError(RuntimeError):
    """Raised when a git invocation fails."""


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
        patch is the conservative answer — the next release isn't a
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


def _run_git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise GitError(
            f"git {' '.join(args)} failed (exit {exc.returncode}): {exc.stderr.strip()}"
        ) from exc
    return result.stdout


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


def latest_tag(cwd: Path, prefix: str) -> str | None:
    """Return the highest semver-sorted tag whose name starts with ``prefix``."""
    out = _run_git(["tag", "--list", f"{prefix}*"], cwd)
    versioned: list[tuple[Version, str]] = []
    for line in out.splitlines():
        name = line.strip()
        if not name.startswith(prefix):
            continue
        try:
            versioned.append((Version(name[len(prefix):]), name))
        except InvalidVersion:
            continue
    if not versioned:
        return None
    versioned.sort(key=lambda pair: pair[0])
    return versioned[-1][1]


def latest_version(cwd: Path, prefix: str) -> Version | None:
    tag = latest_tag(cwd, prefix)
    if tag is None:
        return None
    return Version(tag[len(prefix):])


def latest_stable_tag(cwd: Path, prefix: str) -> str | None:
    """Like :func:`latest_tag` but skips pre-release tags.

    Used by the ``consolidate`` and ``promote`` finalize strategies so the
    final section/stanza enumerates every commit since the previous *stable*
    release rather than just commits since the last RC.
    """
    out = _run_git(["tag", "--list", f"{prefix}*"], cwd)
    versioned: list[tuple[Version, str]] = []
    for line in out.splitlines():
        name = line.strip()
        if not name.startswith(prefix):
            continue
        try:
            v = Version(name[len(prefix):])
        except InvalidVersion:
            continue
        if v.is_prerelease:
            continue
        versioned.append((v, name))
    if not versioned:
        return None
    versioned.sort(key=lambda pair: pair[0])
    return versioned[-1][1]


def commits_since(cwd: Path, since: str | None) -> list[Commit]:
    """List commits between ``since`` (exclusive) and HEAD, in chronological order."""
    return commits_in_range(cwd, since, "HEAD")


def commits_in_range(
    cwd: Path, since: str | None, end: str = "HEAD"
) -> list[Commit]:
    """List commits between ``since`` (exclusive) and ``end`` (inclusive)."""
    range_arg = f"{since}..{end}" if since else end
    try:
        sha_out = _run_git(["rev-list", "--reverse", "--no-merges", range_arg], cwd)
    except GitError:
        return []
    shas = [line.strip() for line in sha_out.splitlines() if line.strip()]

    commits: list[Commit] = []
    for sha in shas:
        message = _run_git(["log", "-1", "--format=%B", sha], cwd).rstrip("\n")
        files_out = _run_git(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", sha], cwd
        )
        files = tuple(line.strip() for line in files_out.splitlines() if line.strip())
        commits.append(parse_commit(sha, message, files))
    return commits


def previous_tag(cwd: Path, prefix: str, current: str) -> str | None:
    """The tag immediately preceding ``current`` for the same prefix."""
    return _adjacent_tag(cwd, prefix, current, stable_only=False)


def previous_stable_tag(cwd: Path, prefix: str, current: str) -> str | None:
    """The previous *stable* (non pre-release) tag for ``prefix``."""
    return _adjacent_tag(cwd, prefix, current, stable_only=True)


def _adjacent_tag(
    cwd: Path, prefix: str, current: str, *, stable_only: bool
) -> str | None:
    out = _run_git(["tag", "--list", f"{prefix}*"], cwd)
    pairs: list[tuple[Version, str]] = []
    for line in out.splitlines():
        name = line.strip()
        if not name.startswith(prefix):
            continue
        try:
            v = Version(name[len(prefix):])
        except InvalidVersion:
            continue
        if stable_only and v.is_prerelease:
            continue
        pairs.append((v, name))
    pairs.sort(key=lambda p: p[0])
    try:
        cur_v = Version(current[len(prefix):])
    except (InvalidVersion, ValueError):
        return None
    prev: str | None = None
    for v, name in pairs:
        if v >= cur_v:
            break
        prev = name
    return prev


def tag_prefix(tag_format: str, component: str) -> str:
    """Render the prefix used to look up tags for ``component``.

    Given ``"{component}-v{version}"`` and ``"api"`` returns ``"api-v"``.
    """
    rendered = tag_format.format(component=component, version="\0VERSION\0")
    head, _, _ = rendered.partition("\0VERSION\0")
    return head
