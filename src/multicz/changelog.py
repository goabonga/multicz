# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Render and insert per-component CHANGELOG.md sections.

A *section* is the chunk of markdown describing a single release for one
component:

    ## [1.3.0] - 2026-04-30

    ### Breaking changes

    - **api**: drop py3.11 (`abc1234`)

    ### Features

    - **api**: add login (`def5678`)

The list of section buckets and their titles is configurable via
``ProjectSettings.changelog_sections`` so each project can pick its own
vocabulary (Features/Fixes vs. keep-a-changelog's Added/Changed/Fixed,
etc.). Commits whose type matches no section are silently dropped — keep
the changelog focused on user-visible changes — unless
``other_section_title`` is set, which buckets them under that title.

When written into an existing file the new section lands directly after
the preamble (anything before the first ``## `` heading) and before any
older release section.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .commits import Commit
from .config import ChangelogSection, _default_changelog_sections


@dataclass(frozen=True)
class CascadeEntry:
    """A non-commit reason for a bump (mirror or trigger), surfaced in
    the changelog so cascade-only releases describe what made them
    happen instead of rendering ``_No notable changes._``.
    """

    upstream: str
    upstream_version: str

_PREAMBLE = (
    "# Changelog\n"
    "\n"
    "All notable changes to this component are documented here.\n"
    "\n"
)


def render_body(
    commits: Iterable[Commit],
    *,
    sections: Sequence[ChangelogSection] | None = None,
    breaking_title: str = "Breaking changes",
    other_title: str = "",
    cascades: Sequence[CascadeEntry] | None = None,
    cascade_title: str = "Dependencies",
    cascade_format: str = "Track `{upstream}` `{upstream_version}`",
) -> str:
    """Render the section bodies (no leading H2).

    Empty string ``breaking_title`` disables the breaking bucket (breaking
    commits then fall through to whichever section claims their type).
    Empty string ``other_title`` drops unmatched conventional commits.

    ``cascades`` lists upstream bumps that pulled this component along
    (mirror writes, trigger edges). When present and ``cascade_title``
    is non-empty, they render as a dedicated H3 section; this also
    suppresses the ``_No notable changes._`` placeholder when no
    commits otherwise apply.
    """
    sections = list(sections) if sections is not None else _default_changelog_sections()
    relevant = [c for c in commits if c.is_conventional]
    cascade_lines: list[str] = []
    if cascades and cascade_title:
        for entry in cascades:
            cascade_lines.append(
                cascade_format.format(
                    upstream=entry.upstream,
                    upstream_version=entry.upstream_version,
                )
            )
    if not relevant and not cascade_lines:
        return "_No notable changes._\n"

    breaking: list[Commit] = []
    if breaking_title:
        breaking = [c for c in relevant if c.breaking]

    buckets: dict[str, list[Commit]] = {}
    breaking_set = {id(c) for c in breaking}
    for section in sections:
        type_set = {t.lower() for t in section.types}
        items = [
            c for c in relevant
            if id(c) not in breaking_set and c.type.lower() in type_set
        ]
        if items:
            buckets[section.title] = items

    if other_title:
        claimed = {t.lower() for s in sections for t in s.types}
        leftovers = [
            c for c in relevant
            if id(c) not in breaking_set and c.type.lower() not in claimed
        ]
        if leftovers:
            buckets[other_title] = leftovers

    ordered: list[tuple[str, list[Commit]]] = (
        [(breaking_title, breaking)] if breaking else []
    )
    for section in sections:
        if section.title in buckets:
            ordered.append((section.title, buckets[section.title]))
    if other_title and other_title in buckets:
        ordered.append((other_title, buckets[other_title]))

    if not ordered and not cascade_lines:
        return "_No notable changes._\n"

    lines: list[str] = []
    for title, items in ordered:
        lines.append(f"### {title}")
        lines.append("")
        for commit in items:
            scope = f"**{commit.scope}**: " if commit.scope else ""
            lines.append(f"- {scope}{commit.subject} (`{commit.sha[:7]}`)")
        lines.append("")
    if cascade_lines:
        lines.append(f"### {cascade_title}")
        lines.append("")
        for entry in cascade_lines:
            lines.append(f"- {entry}")
        lines.append("")
    return "\n".join(lines)


def render_section(
    version: str,
    commits: Iterable[Commit],
    *,
    today: date | None = None,
    sections: Sequence[ChangelogSection] | None = None,
    breaking_title: str = "Breaking changes",
    other_title: str = "",
    cascades: Sequence[CascadeEntry] | None = None,
    cascade_title: str = "Dependencies",
    cascade_format: str = "Track `{upstream}` `{upstream_version}`",
) -> str:
    """Render the markdown for a single release section."""
    when = (today or date.today()).isoformat()
    body = render_body(
        commits,
        sections=sections,
        breaking_title=breaking_title,
        other_title=other_title,
        cascades=cascades,
        cascade_title=cascade_title,
        cascade_format=cascade_format,
    )
    return f"## [{version}] - {when}\n\n" + body


def insert_section(existing: str, section: str) -> str:
    """Insert ``section`` into ``existing``, separating it from neighbouring
    sections with a blank line.
    """
    if not existing.strip():
        return _PREAMBLE + section.rstrip() + "\n"

    lines = existing.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("## "):
            block = section.rstrip("\n") + "\n\n"
            return "".join(lines[:index]) + block + "".join(lines[index:])

    return existing.rstrip("\n") + "\n\n" + section.rstrip() + "\n"


def drop_prerelease_sections(text: str, base_version: str) -> str:
    """Remove markdown sections whose H2 heading is ``[<base_version>-<pre>.<n>]``.

    Used by the ``promote`` finalize strategy so that once ``[1.3.0]`` is
    written, the now-superseded ``[1.3.0-rc.1]``, ``[1.3.0-rc.2]``, …
    sections are removed from the file.
    """
    pre_re = re.compile(
        rf"^## \[{re.escape(base_version)}-[A-Za-z]+\.\d+\]"
    )
    out: list[str] = []
    skip = False
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            skip = bool(pre_re.match(line))
        if not skip:
            out.append(line)
    return "".join(out)


def update_changelog_file(
    path: Path,
    version: str,
    commits: Iterable[Commit],
    *,
    today: date | None = None,
    sections: Sequence[ChangelogSection] | None = None,
    breaking_title: str = "Breaking changes",
    other_title: str = "",
    drop_prereleases: bool = False,
    cascades: Sequence[CascadeEntry] | None = None,
    cascade_title: str = "Dependencies",
    cascade_format: str = "Track `{upstream}` `{upstream_version}`",
) -> None:
    """Render a new section and merge it into ``path`` (creating the file if needed).

    ``drop_prereleases=True`` removes any prior ``## [<version>-<pre>.<n>]``
    sections from the file before inserting the new release section —
    used by the ``promote`` finalize strategy.
    """
    section = render_section(
        version,
        commits,
        today=today,
        sections=sections,
        breaking_title=breaking_title,
        other_title=other_title,
        cascades=cascades,
        cascade_title=cascade_title,
        cascade_format=cascade_format,
    )
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if drop_prereleases:
        existing = drop_prerelease_sections(existing, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(insert_section(existing, section), encoding="utf-8")
