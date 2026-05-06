# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Check: detect when multiple components claim the same file."""

from __future__ import annotations

from collections.abc import Iterator

import pathspec

from ._base import Finding, Level, ValidationContext
from ._git import _list_tracked_files


class PathOverlapCheck:
    """Detect when multiple components claim the same file.

    The reported level - and whether the finding is reported at all -
    depends on ``project.overlap_policy``:

    * ``error`` (default): refuse to plan/bump until the user resolves
      the overlap. Most predictable for newcomers.
    * ``first-match``: surface as a warning. The first-declared
      component wins, the others silently lose. Backwards-compatible
      with multicz before this knob existed.
    * ``allow``: same runtime behavior as ``first-match`` but the
      finding is suppressed (you've explicitly accepted the overlap).
    * ``all``: surface as info. A shared file bumps every claiming
      component (see :meth:`ComponentMatcher.match_all`).
    """

    name = "path_overlap"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        config = ctx.config
        repo = ctx.repo
        policy = config.project.overlap_policy
        if policy == "allow":
            return

        files = _list_tracked_files(repo)
        if not files:
            return

        includes = {
            name: pathspec.PathSpec.from_lines("gitignore", comp.paths)
            for name, comp in config.components.items()
        }
        excludes = {
            name: pathspec.PathSpec.from_lines("gitignore", comp.exclude_paths)
            for name, comp in config.components.items()
        }

        seen: dict[tuple[str, str], str] = {}
        for f in files:
            owners = [
                n
                for n in config.components
                if includes[n].match_file(f) and not excludes[n].match_file(f)
            ]
            if len(owners) <= 1:
                continue
            winner = owners[0]
            for loser in owners[1:]:
                seen.setdefault((winner, loser), f)

        if not seen:
            return

        level: Level
        if policy == "error":
            level = "error"
            suffix = (
                "Set overlap_policy = 'first-match', 'allow', or 'all' to "
                "accept it, or tighten the paths / add an exclude_paths entry."
            )
        elif policy == "first-match":
            level = "warning"
            suffix = (
                "first-match-wins means the earlier-declared component owns "
                "the shared files."
            )
        else:  # all
            level = "info"
            suffix = (
                "overlap_policy = 'all' is in effect - every claiming "
                "component bumps when the shared file changes."
            )

        for (winner, loser), sample in seen.items():
            yield Finding(
                level=level,
                check="path_overlap",
                component=loser,
                message=(
                    f"shares files with {winner!r} (e.g. {sample!r}). {suffix}"
                ),
            )
