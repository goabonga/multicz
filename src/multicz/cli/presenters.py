# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Output renderers for every multicz command.

Each command's compute path produces a structured value (a ``Plan``,
a list of ``Finding``s, a dict of bump results, ...) and hands it to a
presenter function here. Presenters know about Rich tables, JSON
shaping, markdown formatting; commands don't.

Presenters are pure output-writers: they never load config, build a
plan, or talk to git. They take whatever has already been computed
and render it to ``console`` / ``stdout``.
"""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from ..changelog import render_body
from . import console
from ._shared import _append_step_summary

# ============ plan / status ============


def render_plan(plan_obj, config, *, output: str) -> None:
    """Render a bump plan in the requested format.

    ``output`` is one of ``"text"`` or ``"json"``. The markdown summary
    form is handled separately via :func:`append_plan_summary` because
    it writes to a file path, not the console.

    ``config`` is required because the JSON form embeds per-component
    rendered artifact refs.
    """
    if output == "json":
        payload = {
            "schema_version": 1,
            "bumps": {
                bump.component: {
                    "current_version": str(bump.current),
                    "next_version": bump.next,
                    "kind": bump.kind,
                    "reasons": [r.to_dict() for r in bump.reasons],
                    "artifacts": [
                        a.render(component=bump.component, version=bump.next)
                        for a in config.components[bump.component].artifacts
                    ],
                }
                for bump in plan_obj
            },
        }
        console.print_json(data=payload)
        return

    if not plan_obj:
        console.print("[dim]no bumps pending[/]")
        return

    for bump in plan_obj:
        header = (
            f"[bold]{bump.component}[/]: "
            f"{bump.current} → {bump.next} "
            f"[cyan]({bump.kind})[/]"
        )
        console.print(header)
        for reason in bump.reasons:
            console.print(f"  • {reason.summary()}")
        console.print()


def append_plan_summary(path: Path, plan_obj, *, header: str) -> None:
    """Render a plan as a markdown summary and append it to ``path``."""
    lines = [f"## {header}", ""]
    if not plan_obj:
        lines.append("_No bumps pending._")
        _append_step_summary(path, lines)
        return

    lines.extend([
        "| component | current | next | kind |",
        "|---|---|---|---|",
    ])
    for bump in plan_obj:
        lines.append(
            f"| `{bump.component}` | `{bump.current}` | "
            f"`{bump.next}` | {bump.kind} |"
        )
    lines.append("")
    for bump in plan_obj:
        lines.append(
            f"### `{bump.component}` - {bump.current} → {bump.next} "
            f"({bump.kind})"
        )
        lines.append("")
        for reason in bump.reasons:
            lines.append(f"- {reason.summary()}")
        lines.append("")
    _append_step_summary(path, lines)


def render_status_table(plan_obj) -> None:
    """Compact rich.Table for ``multicz status``."""
    if not plan_obj:
        console.print("[dim]no bumps pending[/]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("component")
    table.add_column("current")
    table.add_column("→")
    table.add_column("next")
    table.add_column("kind")
    table.add_column("reasons", overflow="fold")
    for bump in plan_obj:
        table.add_row(
            bump.component,
            str(bump.current),
            "→",
            str(bump.next),
            bump.kind,
            "\n".join(bump.reason_summaries()),
        )
    console.print(table)


# ============ bump ============


def render_bump_empty(*, output: str) -> None:
    """Render the "no bumps pending" early-exit for ``multicz bump``."""
    if output == "json":
        console.print_json(data={"bumps": {}})
    else:
        console.print(
            "[dim]no bumps pending - "
            "use [bold]--force <name>:<kind>[/] for a manual bump[/]"
        )


def render_bump_result(
    applied: dict[str, dict[str, str]],
    config,
    git_summary: dict,
    changelogs_updated: list[str],
    tags_created: list[str],
    *,
    output: str,
    dry_run: bool,
) -> None:
    """Render the post-write result of a ``multicz bump`` invocation."""
    if output == "json":
        bumps_payload = {
            name: {
                "current_version": info["current"],
                "next_version": info["next"],
                "kind": info["kind"],
                "artifacts": [
                    a.render(component=name, version=info["next"])
                    for a in config.components[name].artifacts
                ],
            }
            for name, info in applied.items()
        }
        console.print_json(
            data={
                "schema_version": 1,
                "bumps": bumps_payload,
                "dry_run": dry_run,
                "git": git_summary,
                "changelogs": changelogs_updated,
            }
        )
        return

    verb = "would bump" if dry_run else "bumped"
    for name, info in applied.items():
        console.print(
            f"[green]{verb}[/] [bold]{name}[/] "
            f"{info['current']} → {info['next']} "
            f"([cyan]{info['kind']}[/])"
        )
    if changelogs_updated:
        console.print(
            f"[green]updated changelog[/] {', '.join(changelogs_updated)}"
        )
    if git_summary.get("commit"):
        console.print(f"[green]committed[/] {git_summary['commit'][:7]}")
    if tags_created:
        console.print(f"[green]tagged[/] {', '.join(tags_created)}")
    if git_summary.get("pushed"):
        console.print("[green]pushed[/]")


def append_bump_summary(
    path: Path,
    applied: dict,
    config,
    git_summary: dict,
    *,
    dry_run: bool,
) -> None:
    """Render the applied bump (post-write) as a markdown summary."""
    header = "Released" if not dry_run else "Would release"
    lines = [f"## {header}", ""]
    if not applied:
        lines.append("_No bumps pending._")
        _append_step_summary(path, lines)
        return

    lines.extend([
        "| component | current | next | kind | tag |",
        "|---|---|---|---|---|",
    ])
    tags = git_summary.get("tags") or []
    tag_index = {t.split("-v", 1)[0] if "-v" in t else None: t for t in tags}
    # Fall back to format string lookup when tag_format isn't `<comp>-v<ver>`.
    for name, info in applied.items():
        tag = tag_index.get(name) or "-"
        for t in tags:
            if config.tag_format_for(name).format(
                component=name, version=info["next"]
            ) == t:
                tag = t
                break
        lines.append(
            f"| `{name}` | `{info['current']}` | `{info['next']}` | "
            f"{info['kind']} | `{tag}` |"
        )
    lines.append("")
    if git_summary.get("commit"):
        lines.append(f"**Release commit:** `{git_summary['commit'][:12]}`")
    if tags:
        lines.append(
            f"**Tags created:** {', '.join(f'`{t}`' for t in tags)}"
        )
    if git_summary.get("pushed"):
        lines.append("**Pushed:** yes")
    if git_summary.get("signed_commit"):
        lines.append("**Signed commit:** yes")
    if git_summary.get("signed_tags"):
        lines.append("**Signed tags:** yes")
    _append_step_summary(path, lines)


# ============ changed ============


def render_changed(
    changed_list: list[str],
    unchanged_list: list[str],
    *,
    output: str,
) -> None:
    """Render the output of ``multicz changed``."""
    if output == "json":
        console.print_json(
            data={"changed": changed_list, "unchanged": unchanged_list}
        )
        return

    for name in changed_list:
        print(name)


# ============ explain ============


def render_explain(component: str, bump) -> None:
    """Render ``multicz explain`` output for a single component bump.

    ``bump`` may be ``None`` when no bump is pending - the caller decides
    whether to even call this function in that case (and how).
    """
    # Local imports to keep the presenter module's import graph small.
    from ..planner import CommitReason, MirrorReason, TriggerReason

    if bump is None:
        console.print(
            f"[bold]{component}[/]: [dim]no bump pending - "
            "no relevant commits since the last tag[/]"
        )
        return

    console.print(f"[bold]Component:[/] {component}")
    console.print(f"  Current version: {bump.current}")
    console.print(
        f"  Next version:    {bump.next} [cyan]({bump.kind})[/]"
    )
    if bump.pre:
        console.print(f"  Pre-release:     {bump.pre}")
    if bump.finalize:
        console.print("  Finalize:        yes")
    console.print()
    console.print("[bold]Reasons:[/]")
    for index, reason in enumerate(bump.reasons, start=1):
        if isinstance(reason, CommitReason):
            console.print(f"  {index}. {reason.summary()}")
            console.print(f"      SHA:   {reason.sha}")
            scope = f"({reason.scope})" if reason.scope else ""
            console.print(
                f"      Type:  {reason.type}{scope} → {reason.bump_kind}"
            )
            if reason.original_kind is not None:
                console.print(
                    f"      [yellow]Demoted from {reason.original_kind} "
                    "(bump_policy='scoped', different scope)[/]"
                )
            if reason.breaking:
                console.print("      Breaking: yes")
            console.print("      Files matched in this component:")
            for path in reason.files:
                console.print(f"        - {path}")
        elif isinstance(reason, TriggerReason):
            console.print(f"  {index}. {reason.summary()}")
            console.print(f"      Upstream:      {reason.upstream}")
            console.print(f"      Upstream kind: {reason.upstream_kind}")
        elif isinstance(reason, MirrorReason):
            console.print(f"  {index}. {reason.summary()}")
            console.print(f"      Upstream: {reason.upstream}")
            target = reason.file
            if reason.key:
                target += f":{reason.key}"
            console.print(f"      Wrote:    {target}")
        else:  # ManualReason
            console.print(f"  {index}. {reason.summary()}")


# ============ artifacts ============


def render_artifacts(payload: dict[str, dict], *, output: str) -> None:
    """Render the output of ``multicz artifacts``."""
    if output == "json":
        console.print_json(data=payload)
        return

    for name, data in payload.items():
        if not data["artifacts"]:
            console.print(f"[dim]{name}: no artifacts declared[/]")
            continue
        console.print(f"[bold]{name}[/] ({data['version']})")
        for a in data["artifacts"]:
            console.print(f"  [{a['type']}] {a['ref']}")


# ============ release-notes ============


def render_release_notes_empty(*, output: str) -> None:
    """Render the "nothing to release" early-exit for ``release-notes``."""
    if output == "json":
        console.print_json(data={"sections": []})
    else:
        console.print("[dim]nothing to release[/]")


def render_release_notes_no_pending(name: str) -> None:
    """Render the "no pending bump" message for a single-component invocation."""
    console.print(f"[dim]no pending bump for {name}[/]")


def render_release_notes(
    sections: list[dict],
    config,
    *,
    output: str,
    multi: bool,
) -> None:
    """Render the output of ``multicz release-notes``."""
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
            chunks.append(
                f"## {s['component']} {range_label}\n\n{body}".rstrip() + "\n"
            )
        else:
            chunks.append(body.rstrip() + "\n")
    print("\n".join(chunks).rstrip() + "\n")


# ============ changelog ============


def render_changelog(
    entries: list[dict],
    config,
    *,
    output: str,
) -> None:
    """Render the output of ``multicz changelog``.

    ``entries`` is a list of dicts with keys:

    * ``component``  - component name
    * ``since``      - prior tag (or ``None``)
    * ``relevant``   - filtered list of conventional commits
    * ``planned``    - the planner's PlannedBump (or ``None``)
    """
    if output == "md":
        md_chunks: list[str] = []
        for entry in entries:
            name = entry["component"]
            since = entry["since"]
            relevant = entry["relevant"]
            planned = entry["planned"]
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
        print(
            "\n".join(chunk.rstrip() + "\n" for chunk in md_chunks).rstrip() + "\n"
        )
        return

    # text
    for entry in entries:
        name = entry["component"]
        since = entry["since"]
        relevant = entry["relevant"]
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


# ============ validate ============


def render_validate(
    findings,
    errors,
    warnings,
    infos,
    *,
    output: str,
) -> None:
    """Render the findings of ``multicz validate``.

    The exit-code decision (0 / 1 / 2) stays in the command - this
    presenter only prints.
    """
    if output == "json":
        console.print_json(data={
            "findings": [f.to_dict() for f in findings],
            "summary": {
                "errors": len(errors),
                "warnings": len(warnings),
                "info": len(infos),
            },
        })
        return

    if not findings:
        console.print("[green]✓ no issues found[/]")
        return

    colors = {"error": "red", "warning": "yellow", "info": "blue"}
    tags = {"error": "✗", "warning": "!", "info": "i"}
    for finding in findings:
        color = colors[finding.level]
        tag = tags[finding.level]
        comp = (
            f"[bold]{finding.component}[/]: "
            if finding.component
            else ""
        )
        console.print(
            f"[{color}]{tag}[/] {comp}{finding.message}  "
            f"[dim]({finding.check})[/]"
        )
    console.print()
    counts: list[str] = []
    if errors:
        counts.append(
            f"[red]{len(errors)} error{'s' if len(errors) != 1 else ''}[/]"
        )
    if warnings:
        counts.append(
            f"[yellow]{len(warnings)} "
            f"warning{'s' if len(warnings) != 1 else ''}[/]"
        )
    if infos:
        counts.append(f"[blue]{len(infos)} info[/]")
    console.print(", ".join(counts))


# ============ state ============


def render_state_missing(state_file: str, *, output: str) -> None:
    """Render the "state file not yet written" case."""
    if output == "json":
        console.print_json(data=None)
    else:
        console.print(f"[dim]{state_file} not yet written[/]")


def render_state(state_obj, state_file: str, *, output: str) -> None:
    """Render a populated state file."""
    if output == "json":
        console.print_json(data=state_obj.to_dict())
        return

    console.print(
        f"[bold]state[/] {state_file} "
        f"(schema v{state_obj.version})"
    )
    console.print(
        f"  git_head:  {state_obj.git_head_short or state_obj.git_head}"
    )
    console.print(f"  timestamp: {state_obj.timestamp}")
    for name, comp in state_obj.components.items():
        line = f"  [bold]{name}[/]: {comp.version}"
        if comp.tag:
            line += f"  [dim]({comp.tag})[/]"
        console.print(line)


# ============ init --detect ============


def render_init_detect(components: dict, *, output: str) -> None:
    """Render the ``multicz init --detect`` summary."""
    if output == "json":
        payload = {
            name: {
                "paths": list(c.paths),
                "format": c.format,
                "bump_files": [
                    {"file": str(b.file), "key": b.key}
                    for b in c.bump_files
                ],
                "mirrors": [
                    {"file": str(m.file), "key": m.key}
                    for m in c.mirrors
                ],
                "changelog": str(c.changelog) if c.changelog else None,
            }
            for name, c in components.items()
        }
        console.print_json(data=payload)
        return

    console.print(f"[bold]Detected {len(components)} component(s):[/]")
    for name, comp in components.items():
        primary = comp.bump_files[0].file if comp.bump_files else None
        line = f"  • [bold]{name}[/]"
        if primary is not None:
            line += f" [dim]({primary.as_posix()})[/]"
        elif comp.format == "debian":
            line += " [dim](debian/changelog)[/]"
        else:
            line += " [dim](tag-driven)[/]"
        if comp.format != "default":
            line += f" [yellow]format={comp.format}[/]"
        if comp.mirrors:
            targets = ", ".join(
                f"{m.file.as_posix()}:{m.key}" if m.key else m.file.as_posix()
                for m in comp.mirrors
            )
            line += f"\n      mirrors → {targets}"
        console.print(line)


def render_init_wrote(target: Path, *, bare: bool, components: dict | None) -> None:
    """Render the post-write success message for ``multicz init``."""
    console.print(
        f"[green]wrote[/] {target}"
        f"{' [dim](bare stub)[/]' if bare else ''}"
    )
    if components is not None:
        console.print(f"[dim]detected:[/] {', '.join(components)}")
