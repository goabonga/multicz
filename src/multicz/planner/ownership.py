# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Decide which of a commit's files belong to a component.

The planner, the changelog writer and ``release-notes`` must agree on
this, otherwise a component can bump for a commit that its changelog
then leaves out: the release reads "No notable changes" while the plan
had a concrete reason. Every caller goes through :func:`owned_files`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..config import ComponentMatcher, Config
from ..plugins import run_affects


def owned_files(
    config: Config,
    repo: Path,
    matcher: ComponentMatcher,
    name: str,
    files: Sequence[str],
) -> tuple[str, ...]:
    """Return the files of a commit that attribute it to ``name``.

    Path globs decide first, honouring ``overlap_policy = "all"`` so a
    file shared by several components belongs to each of them. When no
    path matches, an active plugin's :meth:`Plugin.affects` gets a say;
    if it claims the component, every file of the commit is attributed
    to it. An empty tuple means the commit does not touch ``name``.
    """
    if config.project.overlap_policy == "all":
        owned = tuple(p for p in files if name in matcher.match_all(p))
    else:
        owned = tuple(p for p in files if matcher.match(p) == name)
    if not owned and files and run_affects(config, repo, name, list(files)):
        owned = tuple(files)
    return owned
