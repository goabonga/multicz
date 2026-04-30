"""Render and insert per-component CHANGELOG.md sections.

A *section* is the chunk of markdown describing a single release for one
component:

    ## [1.3.0] - 2026-04-30

    ### Features

    - **api**: add login (`abc1234`)

    ### Fixes

    - null token (`def5678`)

When written into an existing file, the new section lands directly after
the preamble (anything before the first ``## `` heading) and before any
older release section, preserving keep-a-changelog ordering.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

from .commits import Commit

_PREAMBLE = (
    "# Changelog\n"
    "\n"
    "All notable changes to this component are documented here.\n"
    "\n"
)

_SECTION_ORDER: tuple[tuple[str, set[str]], ...] = (
    ("Breaking changes", set()),  # special: any commit with breaking=True
    ("Features", {"feat"}),
    ("Fixes", {"fix"}),
    ("Performance", {"perf"}),
    ("Other", set()),  # special: anything conventional that doesn't match above
)


def _bucket(commit: Commit) -> str:
    if commit.breaking:
        return "Breaking changes"
    t = commit.type.lower()
    if t == "feat":
        return "Features"
    if t == "fix":
        return "Fixes"
    if t == "perf":
        return "Performance"
    return "Other"


def render_section(
    version: str,
    commits: Iterable[Commit],
    *,
    today: date | None = None,
) -> str:
    """Render the markdown for a single release section."""
    when = (today or date.today()).isoformat()
    relevant = [c for c in commits if c.is_conventional]
    lines = [f"## [{version}] - {when}", ""]
    if not relevant:
        lines.append("_No notable changes._")
        lines.append("")
        return "\n".join(lines)

    buckets: dict[str, list[Commit]] = {title: [] for title, _ in _SECTION_ORDER}
    for commit in relevant:
        buckets[_bucket(commit)].append(commit)

    for title, _ in _SECTION_ORDER:
        items = buckets[title]
        if not items:
            continue
        lines.append(f"### {title}")
        lines.append("")
        for commit in items:
            scope = f"**{commit.scope}**: " if commit.scope else ""
            lines.append(f"- {scope}{commit.subject} (`{commit.sha[:7]}`)")
        lines.append("")
    return "\n".join(lines)


def insert_section(existing: str, section: str) -> str:
    """Insert ``section`` (which already ends in a blank line) into ``existing``.

    Empty file -> render the keep-a-changelog preamble plus the section.
    Existing ``## `` heading -> insert before it.
    No headings -> append after the existing content with a blank line.
    """
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
) -> None:
    """Render a new section and merge it into ``path`` (creating the file if needed)."""
    section = render_section(version, commits, today=today)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(insert_section(existing, section), encoding="utf-8")
