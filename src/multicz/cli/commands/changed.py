# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz changed`` - list components whose files changed."""

from __future__ import annotations

import re

import typer

from ...commits import commits_since, latest_tag, tag_prefix
from ...config import ComponentMatcher
from .. import app, presenters
from .._shared import _commit_header, _load
from ..results import ChangedReport


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

    direct_changed: set[str] = set()
    for name in config.components:
        if since is None:
            prefix = tag_prefix(config.tag_format_for(name), name)
            ref: str | None = latest_tag(repo, prefix)
        else:
            ref = since
        commits = commits_since(repo, ref)
        for c in commits:
            if release_re.match(_commit_header(c)):
                continue
            if any(matcher.match(f) == name for f in c.files):
                direct_changed.add(name)
                break

    # Cascade closure — propagate ``mirrors`` and ``depends_on`` edges
    # so the output matches what ``multicz plan`` would actually bump.
    # Without this, CI gating by ``changed`` misses cascade-only bumps:
    # e.g. an api source change cascade-bumps chart-api via the
    # appVersion ``mirror`` declared in the config, but the chart files
    # themselves don't appear in the diff, so chart-api would otherwise
    # stay in ``unchanged`` even though it WILL bump at release time.
    changed_list = _propagate_cascades(config, matcher, direct_changed)
    unchanged_list = [n for n in config.components if n not in set(changed_list)]

    presenters.render_changed(
        ChangedReport(
            changed=tuple(changed_list),
            unchanged=tuple(unchanged_list),
        ),
        output=output,
    )


def _propagate_cascades(
    config,
    matcher: ComponentMatcher,
    seed: set[str],
) -> list[str]:
    """Transitively close ``seed`` over ``mirrors`` + ``depends_on``.

    Mirrors a component file into another component's tracked path,
    so a bump on the upstream component writes (and therefore bumps)
    the downstream one — same logic as
    :func:`multicz.planner.build._mirror_pass`, simplified to "which
    components are affected" instead of "what kind of bump".

    ``depends_on`` declares an upstream → downstream cascade (the
    planner's ``_triggers_pass``); identical closure here.

    Returns the components in the same order as
    ``config.components`` (insertion order from the TOML) so the
    output is deterministic regardless of how the set was reached.
    """
    closure = set(seed)
    changed = True
    while changed:
        changed = False
        for name, comp in config.components.items():
            if name in closure:
                for mirror in comp.mirrors:
                    target = matcher.match(str(mirror.file))
                    if target is not None and target != name and target not in closure:
                        closure.add(target)
                        changed = True
            if name not in closure:
                for upstream in comp.depends_on:
                    if upstream in closure:
                        closure.add(name)
                        changed = True
                        break
    return [n for n in config.components if n in closure]
