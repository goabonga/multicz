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
        if self.breaking:
            return "major"
        if self.type.lower() == "feat":
            return "minor"
        if self.type.lower() in {"fix", "perf"}:
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


def commits_since(cwd: Path, since: str | None) -> list[Commit]:
    """List commits between ``since`` (exclusive) and HEAD, in chronological order."""
    range_arg = f"{since}..HEAD" if since else "HEAD"
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


def tag_prefix(tag_format: str, component: str) -> str:
    """Render the prefix used to look up tags for ``component``.

    Given ``"{component}-v{version}"`` and ``"api"`` returns ``"api-v"``.
    """
    rendered = tag_format.format(component=component, version="\0VERSION\0")
    head, _, _ = rendered.partition("\0VERSION\0")
    return head
