# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Conventional Commit parsing over a git history range.

Resolves the latest tag matching a component's tag prefix, lists the commits
since that tag (or the entire history if no tag exists), and parses each
commit header into a :class:`Commit` with the implied semver bump kind.

The implementation lives in two submodules:

* :mod:`multicz.commits.parse` - regexes, the :class:`Commit` dataclass and
  pure-string helpers (no I/O).
* :mod:`multicz.commits.git` - subprocess-backed git queries that return
  parsed commits.
"""

from __future__ import annotations

from .git import (
    GitError,
    commits_in_range,
    commits_since,
    latest_stable_tag,
    latest_tag,
    latest_version,
    previous_stable_tag,
    previous_tag,
)
from .parse import (
    DEFAULT_TYPES,
    BumpKind,
    Commit,
    parse_commit,
    tag_prefix,
    validate_message,
)

__all__ = [
    "DEFAULT_TYPES",
    "BumpKind",
    "Commit",
    "GitError",
    "commits_in_range",
    "commits_since",
    "latest_stable_tag",
    "latest_tag",
    "latest_version",
    "parse_commit",
    "previous_stable_tag",
    "previous_tag",
    "tag_prefix",
    "validate_message",
]
