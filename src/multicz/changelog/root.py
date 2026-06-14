# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Render and insert the project-root aggregated ``CHANGELOG.md``.

The per-component renderer (:mod:`multicz.changelog.markdown`) writes
one file per component, scoped to that component's commits. Useful for
the component's own ``packages/<comp>/CHANGELOG.md``, but it leaves
readers having to open N files to see what a release commit actually
touched across the workspace.

The root renderer fixes that by writing a single section per release
commit at the project root. The section enumerates every component
that bumped + a type-grouped digest of the driving commits, with a
``**<comp>**:`` prefix on each bullet so the source component is
visible at a glance.

Shape:

    ## YYYY-MM-DD

    ### Releases

    - **api** patch — 0.2.2 → 0.2.3
    - **chart-api** patch — 1.0.5 → 1.0.6  _(cascade from api 0.2.3)_

    ### Features

    - **api**: PKCE in OIDC discovery (`04de3e6`)

    ### Fixes

    - **api**: advertise scopes_supported (`8c4567b`)
    - **web**: cap password input length client-side (`ce1484e`)

When all bumps on a release are cascade-only (no driving commits in
any component), the type-grouped sections are skipped and only the
``Releases`` list is rendered — same "explain *why* the release
exists" rationale as the per-component cascade fallback.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..commits import BumpRule, Commit
from ..config import ChangelogSection, _default_changelog_sections
from .bucket import bucket_commits
from .markdown import insert_section

_ROOT_PREAMBLE = (
    "# Changelog\n"
    "\n"
    "All notable changes across components, aggregated per release.\n"
    "Per-component details live under `packages/<comp>/CHANGELOG.md`.\n"
    "\n"
)


@dataclass(frozen=True)
class ComponentBumpDigest:
    """A component's view inside a root release section.

    Carries everything needed to render one entry: the version delta,
    bump kind, the cascade source if any (rendered as the parenthetical
    on the ``Releases`` line), and the commits that drove the bump
    (rendered into the type-grouped sections, prefixed with the
    component name)."""

    component: str
    current: str
    next_version: str
    kind: str
    cascade_from: str | None  # e.g. "api 0.2.3" when this bump cascaded
    commits: tuple[Commit, ...]


def render_root_section(
    digests: Sequence[ComponentBumpDigest],
    *,
    today: date | None = None,
    sections: Sequence[ChangelogSection] | None = None,
    bump_rules: Mapping[str, BumpRule] | None = None,
    breaking_title: str = "Breaking changes",
    other_title: str = "",
) -> str:
    """Render a single root section aggregating ``digests``.

    The section starts with an ``H2`` date heading, then a ``Releases``
    bullet list of every bump, then type-grouped sections rendered
    across every digest's commits with a ``**<component>**:`` prefix.
    """
    when = (today or date.today()).isoformat()
    sections = list(sections) if sections is not None else _default_changelog_sections()
    bump_rules = dict(bump_rules or {})

    lines: list[str] = [f"## {when}", ""]

    # 1. Releases — one bullet per component bumped, sorted to keep the
    # output deterministic regardless of which order the bump loop
    # walked the components.
    lines.append("### Releases")
    lines.append("")
    for digest in sorted(digests, key=lambda d: d.component):
        suffix = f"  _(cascade from {digest.cascade_from})_" if digest.cascade_from else ""
        lines.append(
            f"- **{digest.component}** {digest.kind} — "
            f"{digest.current} → {digest.next_version}{suffix}"
        )
    lines.append("")

    # 2. Type-grouped sections aggregated across every digest's commits.
    # Build a (section_title -> list[(component, commit)]) view so we
    # can prefix each bullet with the component name.
    per_section: dict[str, list[tuple[str, Commit]]] = {}
    breaking_entries: list[tuple[str, Commit]] = []

    for digest in digests:
        bucketed = bucket_commits(
            digest.commits,
            sections=sections,
            bump_rules=bump_rules,
            other_title=other_title,
        )
        for section in sections:
            for commit in bucketed.by_section.get(section.title, ()):
                per_section.setdefault(section.title, []).append((digest.component, commit))
        if other_title:
            for commit in bucketed.by_section.get(other_title, ()):
                per_section.setdefault(other_title, []).append((digest.component, commit))
        for commit in bucketed.breaking:
            breaking_entries.append((digest.component, commit))

    if breaking_entries:
        lines.append(f"### {breaking_title}")
        lines.append("")
        for component, commit in sorted(breaking_entries, key=lambda e: e[0]):
            lines.append(_render_bullet(component, commit))
        lines.append("")

    for section in sections:
        entries = per_section.get(section.title)
        if not entries:
            continue
        lines.append(f"### {section.title}")
        lines.append("")
        for component, commit in sorted(entries, key=lambda e: e[0]):
            lines.append(_render_bullet(component, commit))
        lines.append("")

    if other_title and per_section.get(other_title):
        lines.append(f"### {other_title}")
        lines.append("")
        for component, commit in sorted(per_section[other_title], key=lambda e: e[0]):
            lines.append(_render_bullet(component, commit))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_bullet(component: str, commit: Commit) -> str:
    """Render a single bulleted line for one (component, commit) pair.

    Mirrors the per-component renderer's shape but adds the component
    prefix so the root view stays scannable even when a release spans
    many components.
    """
    sha = commit.sha[:7] if commit.sha else ""
    sha_suffix = f" (`{sha}`)" if sha else ""
    return f"- **{component}**: {commit.subject}{sha_suffix}"


def update_root_changelog_file(
    path: Path,
    digests: Sequence[ComponentBumpDigest],
    *,
    today: date | None = None,
    sections: Sequence[ChangelogSection] | None = None,
    bump_rules: Mapping[str, BumpRule] | None = None,
    breaking_title: str = "Breaking changes",
    other_title: str = "",
) -> None:
    """Render a new root section and merge it into ``path``.

    Creates the file with the preamble when it doesn't exist yet.
    Inserts the new section right after the preamble (and before any
    older release section) using the same ``insert_section`` helper
    the per-component renderer uses, so the merge semantics match
    across files.
    """
    section = render_root_section(
        digests,
        today=today,
        sections=sections,
        bump_rules=bump_rules,
        breaking_title=breaking_title,
        other_title=other_title,
    )
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if not existing.strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_ROOT_PREAMBLE + section, encoding="utf-8")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(insert_section(existing, section), encoding="utf-8")
