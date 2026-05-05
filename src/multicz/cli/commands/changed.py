# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz changed`` - list components whose files changed."""

from __future__ import annotations

import re

import typer

from ...commits import commits_since, latest_tag, tag_prefix
from ...components import ComponentMatcher
from .. import app, presenters
from .._shared import _commit_header, _load


@app.command()
def changed(
    since: str = typer.Option(
        None, "--since",
        help="Reference to compare against (e.g. origin/main, HEAD~5). "
             "When omitted, each component is compared against its own "
             "last tag - same window as the planner uses for bumps.",
    ),
    output: str = typer.Option(
        "text", "--output", "-o", help="text | json",
    ),
) -> None:
    """List components whose files changed since the given reference.

    Designed for CI matrix gating: only run tests/builds for components
    that actually changed.

    \b
    GitHub Actions example:
      jobs:
        detect:
          outputs:
            changed: ${{ steps.c.outputs.list }}
          steps:
            - id: c
              run: echo "list=$(multicz changed --since origin/main \\
                                 --output json | jq -c .changed)" >> $GITHUB_OUTPUT
        test:
          needs: detect
          strategy:
            matrix:
              component: ${{ fromJson(needs.detect.outputs.changed) }}

    Without --since, the answer is per-component (same window as the
    planner). With --since, every component shares the reference -
    ideal for "what changed in this PR vs main".

    Release commits matching ``project.release_commit_pattern`` are
    filtered out so a previous ``multicz bump --commit`` doesn't keep
    flagging components as changed forever.
    """
    repo, config = _load()
    matcher = ComponentMatcher(config.components)
    release_re = re.compile(config.project.release_commit_pattern)

    changed_list: list[str] = []
    unchanged_list: list[str] = []
    for name in config.components:
        if since is None:
            prefix = tag_prefix(config.tag_format_for(name), name)
            ref: str | None = latest_tag(repo, prefix)
        else:
            ref = since
        commits = commits_since(repo, ref)
        owns_change = False
        for c in commits:
            if release_re.match(_commit_header(c)):
                continue
            for f in c.files:
                if matcher.match(f) == name:
                    owns_change = True
                    break
            if owns_change:
                break
        if owns_change:
            changed_list.append(name)
        else:
            unchanged_list.append(name)

    presenters.render_changed(changed_list, unchanged_list, output=output)
