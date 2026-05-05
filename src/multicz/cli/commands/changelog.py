# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz changelog`` - print per-component conventional commits since the last tag."""

from __future__ import annotations

import typer

from ...changelog import render_body
from ...commits import commits_since, latest_tag, tag_prefix
from ...components import ComponentMatcher
from .. import app, console, err
from .._shared import _build_plan_or_exit, _load


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

    md_chunks: list[str] = []

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

        if output == "md":
            planned = plan.bumps.get(name)
            heading = f"## {name}"
            if planned:
                heading += f" {planned.current} → {planned.next}"
            elif since:
                heading += f" (since {since})"
            body = render_body(
                relevant,
                sections=config.project.changelog_sections,
                breaking_title=config.project.breaking_section_title,
                other_title=config.project.other_section_title,
            )
            md_chunks.append(f"{heading}\n\n{body}")
        else:
            header = f"## {name}"
            if since:
                header += f"  (since {since})"
            console.print(f"\n[bold]{header}[/]")
            if not relevant:
                console.print("  [dim]no changes[/]")
                continue
            for commit in relevant:
                scope = f"({commit.scope})" if commit.scope else ""
                bang = "!" if commit.breaking else ""
                console.print(
                    f"  - {commit.type}{scope}{bang}: {commit.subject}"
                    f"  [dim]({commit.sha[:7]})[/]"
                )

    if output == "md":
        print("\n".join(chunk.rstrip() + "\n" for chunk in md_chunks).rstrip() + "\n")
