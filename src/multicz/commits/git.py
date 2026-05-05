# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Git operations backing commit-history queries.

Resolves the latest tag matching a component's tag prefix, lists the commits
since that tag (or the entire history if no tag exists), and returns parsed
:class:`~multicz.commits.parse.Commit` records via :func:`commits_since` and
:func:`commits_in_range`. All subprocess and filesystem I/O lives here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from packaging.version import InvalidVersion, Version

from .parse import Commit, parse_commit


class GitError(RuntimeError):
    """Raised when a git invocation fails."""


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
