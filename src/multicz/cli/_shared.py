# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Helpers shared across multiple multicz CLI commands."""

from __future__ import annotations

import re
from pathlib import Path

import typer

from ..changelog import CascadeEntry
from ..commits import (
    commits_since,
    latest_stable_tag,
    latest_tag,
    tag_prefix,
)
from ..config import ComponentMatcher, find_config, load_config
from ..planner import (
    MirrorReason,
    NonConventionalCommitsError,
    TriggerReason,
    build_plan,
)
from . import err


def _load() -> tuple[Path, object]:
    from pydantic import ValidationError
    try:
        config_path = find_config()
    except FileNotFoundError as exc:
        err.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc
    try:
        return config_path.parent, load_config(config_path)
    except ValidationError as exc:
        err.print(f"[red]invalid {config_path}:[/]")
        for error in exc.errors():
            loc = " -> ".join(str(p) for p in error["loc"])
            err.print(f"  [yellow]{loc}[/]: {error['msg']}")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        err.print(f"[red]invalid {config_path}:[/] {exc}")
        raise typer.Exit(code=1) from exc


def _parse_force_specs(specs: list[str], config) -> dict[str, str]:
    """Parse ``--force <name>:<kind>`` flags into a dict.

    Validates the component name and kind upfront so the user gets a
    clear error before the planner runs.
    """
    valid_kinds = {"major", "minor", "patch"}
    parsed: dict[str, str] = {}
    for spec in specs or []:
        if ":" not in spec:
            err.print(
                f"[red]invalid --force spec[/] {spec!r}: "
                "expected NAME:KIND (e.g. api:patch)"
            )
            raise typer.Exit(code=1)
        name, _, kind = spec.partition(":")
        if name not in config.components:
            err.print(f"[red]unknown component:[/] {name}")
            raise typer.Exit(code=1)
        if kind not in valid_kinds:
            err.print(
                f"[red]invalid kind[/] {kind!r}: "
                "must be major, minor, or patch"
            )
            raise typer.Exit(code=1)
        parsed[name] = kind
    return parsed


def _append_step_summary(path: Path, lines: list[str]) -> None:
    """Append a markdown block to ``path``.

    Mirrors GitHub Actions' ``$GITHUB_STEP_SUMMARY`` semantics: each
    step's content is appended; the runner concatenates everything into
    the workflow's run-page summary. Safe to call from local shells -
    the file is just a text file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")


def _build_plan_or_exit(repo, config, **kwargs):
    """Wrap build_plan() and surface NonConventionalCommitsError as a clean
    typer.Exit instead of a raw traceback."""
    try:
        return build_plan(repo, config, **kwargs)
    except NonConventionalCommitsError as exc:
        err.print(
            f"[red]✗ {len(exc.offenders)} non-conventional commit(s) "
            "blocking the plan[/] [dim](unknown_commit_policy='error')[/]"
        )
        for sha, subject in exc.offenders:
            err.print(f"  - {sha[:7]}: {subject}")
        err.print(
            "\n[dim]Either rewrite their headers as conventional commits "
            "(`git rebase -i`), or set "
            "[bold]unknown_commit_policy = \"ignore\"[/] (or "
            "[bold]\"patch\"[/]) in [project].[/]"
        )
        raise typer.Exit(code=1) from exc


def _commit_header(commit) -> str:
    if commit.scope:
        return f"{commit.type}({commit.scope}): {commit.subject}"
    return f"{commit.type}: {commit.subject}"


def _component_relevant_commits(
    name: str,
    config,  # Config
    repo: Path,
    matcher: ComponentMatcher,
    *,
    since_stable: bool = False,
):
    """Conventional commits owning ``name`` since the component's last tag.

    Filters applied:

    * release commits matching ``project.release_commit_pattern`` are
      skipped so the chore(release) lines don't pollute the changelog.
    * commits whose effective ``bump_rules`` entry is ``"none"`` (i.e.
      explicitly silenced, including breaking variants) are skipped
      entirely.

    When ``since_stable`` is True, the range starts at the previous
    *stable* tag instead - used by the ``consolidate`` and ``promote``
    finalize strategies.
    """
    prefix = tag_prefix(config.tag_format_for(name), name)
    since = (
        latest_stable_tag(repo, prefix)
        if since_stable
        else latest_tag(repo, prefix)
    )
    release_re = re.compile(config.project.release_commit_pattern)
    ignored = config.ignored_types_for(name)
    return [
        c
        for c in commits_since(repo, since)
        if c.is_conventional
        and not release_re.match(_commit_header(c))
        and c.type.lower() not in ignored
        and any(matcher.match(f) == name for f in c.files)
    ]


def _cascade_entries_for(planned, plan, config) -> list[CascadeEntry]:
    """Build cascade entries from a planned bump's mirror/trigger reasons.

    Used by both ``bump`` (when writing the downstream CHANGELOG.md) and
    ``release-notes`` (when rendering markdown for ``gh release create``)
    so the two surfaces stay in sync.

    For each ``MirrorReason``, looks up the matching mirror declaration
    on the upstream component to pick up the optional
    ``changelog_section`` / ``changelog_format`` overrides. Trigger
    cascades have no such customization handle and always fall through
    to the project-level defaults. The first reason wins per upstream
    (existing dedup behavior).
    """
    entries: list[CascadeEntry] = []
    seen_upstreams: set[str] = set()
    for reason in planned.reasons:
        if not isinstance(reason, MirrorReason | TriggerReason):
            continue
        if reason.upstream in seen_upstreams:
            continue
        upstream_planned = plan.bumps.get(reason.upstream)
        if upstream_planned is None:
            continue
        section_override: str | None = None
        format_override: str | None = None
        if isinstance(reason, MirrorReason):
            upstream_component = config.components.get(reason.upstream)
            if upstream_component is not None:
                for mirror in upstream_component.mirrors:
                    if (
                        str(mirror.file) == reason.file
                        and mirror.key == reason.key
                    ):
                        section_override = mirror.changelog_section
                        format_override = mirror.changelog_format
                        break
        entries.append(
            CascadeEntry(
                upstream=reason.upstream,
                upstream_version=upstream_planned.next,
                section=section_override,
                format=format_override,
            )
        )
        seen_upstreams.add(reason.upstream)
    return entries
