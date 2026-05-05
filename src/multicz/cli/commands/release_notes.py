# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz release-notes`` - generate release notes for a bump or past tag."""

from __future__ import annotations

import re
from pathlib import Path

import typer
from packaging.version import Version

from ...changelog import render_body
from ...commits import (
    commits_in_range,
    previous_stable_tag,
    previous_tag,
    tag_prefix,
)
from ...components import ComponentMatcher
from .. import app, console, err
from .._shared import (
    _build_plan_or_exit,
    _cascade_entries_for,
    _commit_header,
    _component_relevant_commits,
    _load,
)


def _component_for_tag(config, tag: str) -> str | None:
    """Find the component whose tag_format produces a prefix that ``tag`` starts with."""
    best_match: tuple[int, str] | None = None
    for name in config.components:
        prefix = tag_prefix(config.tag_format_for(name), name)
        if tag.startswith(prefix):
            # Prefer the longest match (more specific prefix wins)
            score = len(prefix)
            if best_match is None or score > best_match[0]:
                best_match = (score, name)
    return best_match[1] if best_match else None


def _filtered_commits_in_range(
    name: str, config, repo: Path, matcher, *, since: str | None, end: str
):
    """Same filtering as _component_relevant_commits but for a custom range."""
    release_re = re.compile(config.project.release_commit_pattern)
    ignored = config.ignored_types_for(name)
    return [
        c
        for c in commits_in_range(repo, since, end)
        if c.is_conventional
        and not release_re.match(_commit_header(c))
        and c.type.lower() not in ignored
        and any(matcher.match(f) == name for f in c.files)
    ]


@app.command(name="release-notes")
def release_notes_cmd(
    component: str = typer.Argument(
        None,
        help="Component to render notes for. Required unless --all or --tag is set.",
    ),
    all_: bool = typer.Option(
        False, "--all",
        help="Render notes for every component with a planned bump.",
    ),
    tag: str = typer.Option(
        None, "--tag",
        help="Render notes for a past release tag (e.g. api-v1.3.0).",
    ),
    output: str = typer.Option(
        "md", "--output", "-o", help="md | text | json",
    ),
) -> None:
    """Generate release notes for an upcoming bump or a past tag.

    Designed for piping into ``gh release create`` or pasting into a
    GitHub/GitLab Release UI: no file is written, the output IS the
    notes.

    \b
    Default (notes for the upcoming bump - same set as `plan`):
      multicz release-notes api
      multicz release-notes --all

    Retrospective (what shipped in a tagged release):
      multicz release-notes --tag api-v1.3.0

    Stable release tags look at commits since the previous *stable*
    tag (so v1.3.0 lists everything since v1.2.0, not just since
    v1.3.0-rc.2). Pre-release tags use the immediately previous tag
    so each rc shows only the delta.
    """
    if tag is None and not all_ and component is None:
        err.print(
            "[red]specify a component, --all, or --tag <tag>[/]"
        )
        raise typer.Exit(code=1)
    if tag is not None and (all_ or component is not None):
        err.print(
            "[red]--tag is exclusive with a component name and --all[/]"
        )
        raise typer.Exit(code=1)

    repo, config = _load()
    matcher = ComponentMatcher(config.components)

    sections: list[dict] = []

    if tag is not None:
        owner = _component_for_tag(config, tag)
        if owner is None:
            err.print(
                f"[red]tag {tag!r} doesn't match any component's tag_format[/]"
            )
            raise typer.Exit(code=1)
        prefix = tag_prefix(config.tag_format_for(owner), owner)
        target_version = Version(tag[len(prefix):])
        if target_version.is_prerelease:
            prev = previous_tag(repo, prefix, tag)
        else:
            prev = previous_stable_tag(repo, prefix, tag)
        commits = _filtered_commits_in_range(
            owner, config, repo, matcher, since=prev, end=tag
        )
        sections.append({
            "component": owner,
            "from": prev,
            "from_version": prev[len(prefix):] if prev else None,
            "to_version": str(target_version),
            "commits": commits,
        })
    else:
        plan_obj = _build_plan_or_exit(repo, config)
        if all_:
            targets = list(plan_obj.bumps)
        else:
            if component not in config.components:
                err.print(f"[red]unknown component:[/] {component}")
                raise typer.Exit(code=1)
            targets = [component]

        for name in targets:
            bump = plan_obj.bumps.get(name)
            if bump is None:
                if not all_:
                    console.print(
                        f"[dim]no pending bump for {name}[/]"
                    )
                    return
                continue
            commits = _component_relevant_commits(name, config, repo, matcher)
            sections.append({
                "component": name,
                "from": None,
                "from_version": str(bump.current),
                "to_version": bump.next,
                "commits": commits,
                # Cascades only attach to upcoming bumps - past tag mode
                # has no plan reasons to draw from.
                "cascades": _cascade_entries_for(bump, plan_obj, config),
            })

    if not sections:
        if output == "json":
            console.print_json(data={"sections": []})
        else:
            console.print("[dim]nothing to release[/]")
        return

    if output == "json":
        console.print_json(data={
            "sections": [
                {
                    "component": s["component"],
                    "from_version": s["from_version"],
                    "to_version": s["to_version"],
                    "commits": [
                        {
                            "sha": c.sha,
                            "type": c.type,
                            "scope": c.scope,
                            "breaking": c.breaking,
                            "subject": c.subject,
                        }
                        for c in s["commits"]
                    ],
                    "cascades": [
                        {
                            "upstream": e.upstream,
                            "upstream_version": e.upstream_version,
                            "section": e.section,
                            "format": e.format,
                        }
                        for e in s.get("cascades") or []
                    ],
                }
                for s in sections
            ]
        })
        return

    if output == "text":
        for s in sections:
            range_label = (
                f"{s['from_version']} → {s['to_version']}"
                if s["from_version"]
                else s["to_version"]
            )
            console.print(f"[bold]{s['component']}[/] {range_label}")
            for c in s["commits"]:
                bang = "!" if c.breaking else ""
                scope = f"({c.scope})" if c.scope else ""
                console.print(
                    f"  - {c.type}{scope}{bang}: {c.subject}  "
                    f"[dim]({c.sha[:7]})[/]"
                )
            console.print()
        return

    # md (default)
    chunks: list[str] = []
    multi = len(sections) > 1 or all_
    for s in sections:
        body = render_body(
            s["commits"],
            sections=config.project.changelog_sections,
            breaking_title=config.project.breaking_section_title,
            other_title=config.project.other_section_title,
            cascades=s.get("cascades"),
            cascade_title=config.project.cascade_section_title,
            cascade_format=config.project.cascade_changelog_format,
        )
        if multi:
            range_label = (
                f"{s['from_version']} → {s['to_version']}"
                if s["from_version"]
                else s["to_version"]
            )
            chunks.append(f"## {s['component']} {range_label}\n\n{body}".rstrip() + "\n")
        else:
            chunks.append(body.rstrip() + "\n")
    print("\n".join(chunks).rstrip() + "\n")
