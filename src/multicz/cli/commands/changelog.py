# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz changelog`` - print per-component conventional commits since the last tag."""

from __future__ import annotations

import typer

from ...commits import commits_since, latest_tag, tag_prefix
from ...components import ComponentMatcher
from .. import app, err, presenters
from .._shared import _build_plan_or_exit, _load
from ..results import ChangelogEntry


@app.command()
def changelog(
    component: str = typer.Option(None, "--component", "-c"),
    output: str = typer.Option("text", "--output", "-o", help="text | md"),
) -> None:
    """Print a per-component log of conventional commits since the last tag."""
    repo, config = _load()
    matcher = ComponentMatcher(config.components)
    names = [component] if component else list(config.components)
    plan = _build_plan_or_exit(repo, config)

    entries: list[ChangelogEntry] = []
    for name in names:
        if name not in config.components:
            err.print(f"[red]unknown component:[/] {name}")
            raise typer.Exit(code=1)
        prefix = tag_prefix(config.tag_format_for(name), name)
        since = latest_tag(repo, prefix)
        relevant = [
            c
            for c in commits_since(repo, since)
            if c.is_conventional and any(matcher.match(f) == name for f in c.files)
        ]
        entries.append(ChangelogEntry(
            component=name,
            since=since,
            relevant=tuple(relevant),
            planned=plan.bumps.get(name),
        ))

    presenters.render_changelog(entries, config, output=output)
