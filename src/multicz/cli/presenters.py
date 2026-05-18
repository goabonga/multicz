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
from .results import (
    BumpResult,
    ChangedReport,
    ChangelogEntry,
    GitSummary,
    ReleaseNotesSection,
    ValidationReport,
)

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


def render_plugin_advice(lines, *, output: str) -> None:
    """Render :meth:`Plugin.status_lines` output — free-form actionable
    text plugins return to inform the user (e.g. "3 deprecations marked
    for removal in v3.0").

    Text output prefixes each line with a magenta arrow so it stands
    out from the bump table without screaming like a violation.
    """
    if output == "json":
        console.print_json(data={"advice": list(lines)})
        return
    if not lines:
        return
    console.print()
    for line in lines:
        console.print(f"  [magenta]→[/] {line}")


def render_plugin_violations(violations, *, output: str) -> None:
    """Render the list of :class:`multicz.plugins.Violation` raised by
    installed plugins after :meth:`Plugin.post_plan`.

    Text output groups by severity (errors first, then warnings, then
    infos) and prefixes each line with the plugin name. JSON output
    emits an array suited for CI consumers.
    """
    if output == "json":
        console.print_json(
            data={
                "violations": [
                    {
                        "severity": v.severity.value,
                        "message": v.message,
                        "plugin": v.plugin,
                        "component": v.component,
                        "file": str(v.file) if v.file else None,
                        "line": v.line,
                    }
                    for v in violations
                ]
            }
        )
        return
    colour = {"error": "red", "warning": "yellow", "info": "cyan"}
    glyph = {"error": "✗", "warning": "!", "info": "·"}
    by_severity: dict[str, list] = {"error": [], "warning": [], "info": []}
    for v in violations:
        by_severity[v.severity.value].append(v)
    for sev in ("error", "warning", "info"):
        for v in by_severity[sev]:
            loc = ""
            if v.file:
                loc = f" [dim]({v.file}{':' + str(v.line) if v.line else ''})[/]"
            comp = f"[dim]\\[{v.component}][/] " if v.component else ""
            console.print(
                f"  [{colour[sev]}]{glyph[sev]}[/] {comp}{v.message}"
                f" [dim](from {v.plugin})[/]" + loc
            )


def _git_summary_to_json(git: GitSummary) -> dict:
    """Project a GitSummary back to the legacy ``git_summary`` dict shape.

    The JSON output for ``multicz bump`` must stay byte-identical with
    the pre-refactor shape: keys appear only when populated, ``tags`` is
    a list, signed flags render as ``"yes"``. Centralised here so the
    table-renderer (``append_bump_summary``) and the JSON renderer share
    one definition.
    """
    out: dict = {}
    if git.commit_sha:
        out["commit"] = git.commit_sha
    if git.tags:
        out["tags"] = list(git.tags)
    if git.signed_tags:
        out["signed_tags"] = "yes"
    if git.signed_commit and git.commit_sha:
        out["signed_commit"] = "yes"
    if git.pushed:
        out["pushed"] = "yes"
    return out


def render_bump_result(
    result: BumpResult,
    config,
    *,
    output: str,
) -> None:
    """Render the post-write result of a ``multicz bump`` invocation."""
    if output == "json":
        bumps_payload = {
            b.component: {
                "current_version": b.current,
                "next_version": b.next,
                "kind": b.kind,
                "artifacts": [
                    a.render(component=b.component, version=b.next)
                    for a in config.components[b.component].artifacts
                ],
            }
            for b in result.bumps
        }
        console.print_json(
            data={
                "schema_version": 1,
                "bumps": bumps_payload,
                "dry_run": result.dry_run,
                "git": _git_summary_to_json(result.git),
                "changelogs": list(result.changelogs),
            }
        )
        return

    verb = "would bump" if result.dry_run else "bumped"
    for b in result.bumps:
        console.print(
            f"[green]{verb}[/] [bold]{b.component}[/] "
            f"{b.current} → {b.next} "
            f"([cyan]{b.kind}[/])"
        )
    if result.changelogs:
        console.print(
            f"[green]updated changelog[/] {', '.join(result.changelogs)}"
        )
    if result.git.commit_sha:
        console.print(f"[green]committed[/] {result.git.commit_sha[:7]}")
    if result.git.tags:
        console.print(f"[green]tagged[/] {', '.join(result.git.tags)}")
    if result.git.pushed:
        console.print("[green]pushed[/]")


def append_bump_summary(
    path: Path,
    result: BumpResult,
    config,
) -> None:
    """Render the applied bump (post-write) as a markdown summary."""
    header = "Released" if not result.dry_run else "Would release"
    lines = [f"## {header}", ""]
    if not result.bumps:
        lines.append("_No bumps pending._")
        _append_step_summary(path, lines)
        return

    lines.extend([
        "| component | current | next | kind | tag |",
        "|---|---|---|---|---|",
    ])
    tags = list(result.git.tags)
    tag_index = {t.split("-v", 1)[0] if "-v" in t else None: t for t in tags}
    # Fall back to format string lookup when tag_format isn't `<comp>-v<ver>`.
    for b in result.bumps:
        tag = tag_index.get(b.component) or "-"
        for t in tags:
            if config.tag_format_for(b.component).format(
                component=b.component, version=b.next
            ) == t:
                tag = t
                break
        lines.append(
            f"| `{b.component}` | `{b.current}` | `{b.next}` | "
            f"{b.kind} | `{tag}` |"
        )
    lines.append("")
    if result.git.commit_sha:
        lines.append(f"**Release commit:** `{result.git.commit_sha[:12]}`")
    if tags:
        lines.append(
            f"**Tags created:** {', '.join(f'`{t}`' for t in tags)}"
        )
    if result.git.pushed:
        lines.append("**Pushed:** yes")
    if result.git.signed_commit and result.git.commit_sha:
        lines.append("**Signed commit:** yes")
    if result.git.signed_tags:
        lines.append("**Signed tags:** yes")
    _append_step_summary(path, lines)


# ============ changed ============


def render_changed(report: ChangedReport, *, output: str) -> None:
    """Render the output of ``multicz changed``."""
    if output == "json":
        console.print_json(
            data={
                "changed": list(report.changed),
                "unchanged": list(report.unchanged),
            }
        )
        return

    for name in report.changed:
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
    sections: list[ReleaseNotesSection],
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
                    "component": s.component,
                    "from_version": s.from_version,
                    "to_version": s.to_version,
                    "commits": [
                        {
                            "sha": c.sha,
                            "type": c.type,
                            "scope": c.scope,
                            "breaking": c.breaking,
                            "subject": c.subject,
                        }
                        for c in s.commits
                    ],
                    "cascades": [
                        {
                            "upstream": e.upstream,
                            "upstream_version": e.upstream_version,
                            "section": e.section,
                            "format": e.format,
                        }
                        for e in s.cascades
                    ],
                }
                for s in sections
            ]
        })
        return

    if output == "text":
        for s in sections:
            range_label = (
                f"{s.from_version} → {s.to_version}"
                if s.from_version
                else s.to_version
            )
            console.print(f"[bold]{s.component}[/] {range_label}")
            for c in s.commits:
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
            list(s.commits),
            sections=config.project.changelog_sections,
            bump_rules=config.bump_rules_for(s.component),
            breaking_title=config.project.breaking_section_title,
            other_title=config.project.other_section_title,
            cascades=list(s.cascades) if s.cascades else None,
            cascade_title=config.project.cascade_section_title,
            cascade_format=config.project.cascade_changelog_format,
            plugin_sections=list(s.plugin_sections) if s.plugin_sections else None,
        )
        if multi:
            range_label = (
                f"{s.from_version} → {s.to_version}"
                if s.from_version
                else s.to_version
            )
            chunks.append(
                f"## {s.component} {range_label}\n\n{body}".rstrip() + "\n"
            )
        else:
            chunks.append(body.rstrip() + "\n")
    print("\n".join(chunks).rstrip() + "\n")


# ============ changelog ============


def render_changelog(
    entries: list[ChangelogEntry],
    config,
    *,
    output: str,
) -> None:
    """Render the output of ``multicz changelog``."""
    if output == "md":
        md_chunks: list[str] = []
        for entry in entries:
            heading = f"## {entry.component}"
            if entry.planned:
                heading += f" {entry.planned.current} → {entry.planned.next}"
            elif entry.since:
                heading += f" (since {entry.since})"
            body = render_body(
                list(entry.relevant),
                sections=config.project.changelog_sections,
                bump_rules=config.bump_rules_for(entry.component),
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
        header = f"## {entry.component}"
        if entry.since:
            header += f"  (since {entry.since})"
        console.print(f"\n[bold]{header}[/]")
        if not entry.relevant:
            console.print("  [dim]no changes[/]")
            continue
        for commit in entry.relevant:
            scope = f"({commit.scope})" if commit.scope else ""
            bang = "!" if commit.breaking else ""
            console.print(
                f"  - {commit.type}{scope}{bang}: {commit.subject}"
                f"  [dim]({commit.sha[:7]})[/]"
            )


# ============ validate ============


def render_validate(report: ValidationReport, *, output: str) -> None:
    """Render the findings of ``multicz validate``.

    The exit-code decision (0 / 1 / 2) stays in the command - this
    presenter only prints.
    """
    if output == "json":
        console.print_json(data={
            "findings": [f.to_dict() for f in report.findings],
            "summary": {
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "info": len(report.infos),
            },
        })
        return

    if not report.findings:
        console.print("[green]✓ no issues found[/]")
        return

    colors = {"error": "red", "warning": "yellow", "info": "blue"}
    tags = {"error": "✗", "warning": "!", "info": "i"}
    for finding in report.findings:
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
    if report.errors:
        counts.append(
            f"[red]{len(report.errors)} "
            f"error{'s' if len(report.errors) != 1 else ''}[/]"
        )
    if report.warnings:
        counts.append(
            f"[yellow]{len(report.warnings)} "
            f"warning{'s' if len(report.warnings) != 1 else ''}[/]"
        )
    if report.infos:
        counts.append(f"[blue]{len(report.infos)} info[/]")
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
                "bump_files": [
                    {"file": str(b.file), "key": b.key}
                    for b in c.bump_files
                ],
                "mirrors": [
                    {"file": str(m.file), "key": m.key}
                    for m in c.mirrors
                ],
                "writers": [
                    {"type": w.type, "file": str(w.file)}
                    for w in c.writers
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
        elif comp.writers:
            first = comp.writers[0]
            line += f" [dim]({first.file.as_posix()})[/]"
        else:
            line += " [dim](tag-driven)[/]"
        if comp.writers:
            kinds = ", ".join(w.type for w in comp.writers)
            line += f" [yellow]writers={kinds}[/]"
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
