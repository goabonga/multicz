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

from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path

from .commits import Commit
from .config import ChangelogSection, _default_changelog_sections

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
) -> str:
    """Render the section bodies (no leading H2).

    Empty string ``breaking_title`` disables the breaking bucket (breaking
    commits then fall through to whichever section claims their type).
    Empty string ``other_title`` drops unmatched conventional commits.
    """
    sections = list(sections) if sections is not None else _default_changelog_sections()
    relevant = [c for c in commits if c.is_conventional]
    if not relevant:
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

    if not ordered:
        return "_No notable changes._\n"

    lines: list[str] = []
    for title, items in ordered:
        lines.append(f"### {title}")
        lines.append("")
        for commit in items:
            scope = f"**{commit.scope}**: " if commit.scope else ""
            lines.append(f"- {scope}{commit.subject} (`{commit.sha[:7]}`)")
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
) -> str:
    """Render the markdown for a single release section."""
    when = (today or date.today()).isoformat()
    body = render_body(
        commits,
        sections=sections,
        breaking_title=breaking_title,
        other_title=other_title,
    )
    return f"## [{version}] - {when}\n\n" + body


def insert_section(existing: str, section: str) -> str:
    """Insert ``section`` (which already ends in a blank line) into ``existing``."""
    if not existing.strip():
        return _PREAMBLE + section.rstrip() + "\n"

    lines = existing.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("## "):
            return "".join(lines[:index]) + section + "".join(lines[index:])

    suffix = "" if existing.endswith("\n") else "\n"
    return existing + suffix + "\n" + section.rstrip() + "\n"


def update_changelog_file(
    path: Path,
    version: str,
    commits: Iterable[Commit],
    *,
    today: date | None = None,
    sections: Sequence[ChangelogSection] | None = None,
    breaking_title: str = "Breaking changes",
    other_title: str = "",
) -> None:
    """Render a new section and merge it into ``path`` (creating the file if needed)."""
    section = render_section(
        version,
        commits,
        today=today,
        sections=sections,
        breaking_title=breaking_title,
        other_title=other_title,
    )
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(insert_section(existing, section), encoding="utf-8")
