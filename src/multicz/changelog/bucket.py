# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Pure commit filtering and section bucketing.

Both the Markdown renderer (``render_body`` in ``__init__.py``) and the
Debian renderer (``render_stanza`` in ``..debian``) used to duplicate the
same "filter conventional commits, bucket by section, decide what
counts as breaking / leftover" logic. This module owns that logic
exactly once. Renderers consume the structured output and only deal
with their own format-specific details (headers, dates, bullet
markers).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from ..commits import BumpRule, Commit
from ..config import ChangelogSection, _default_changelog_sections


@dataclass(frozen=True)
class BucketedCommits:
    """Filter result reorganized for sectioned renderers (markdown).

    * ``breaking`` — commits with the breaking marker, when
      ``breaking_title`` is non-empty. They are *removed* from
      ``by_section`` so a renderer can place them in their own section
      without double-counting.
    * ``by_section`` — ordered mapping of *section title* to the
      commits in that bucket. Iteration order matches the order of
      ``sections`` passed in.
    * ``leftovers`` — commits whose type matches no section (e.g.
      ``chore``, ``docs``). Empty when ``other_title`` is empty
      (default), since the convention is to silently drop those
      commits.
    """

    breaking: list[Commit] = field(default_factory=list)
    by_section: dict[str, list[Commit]] = field(default_factory=dict)
    leftovers: list[Commit] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.breaking and not self.by_section and not self.leftovers


def bucket_commits(
    commits: Iterable[Commit],
    *,
    sections: Sequence[ChangelogSection] | None = None,
    bump_rules: Mapping[str, BumpRule] | None = None,
    breaking_title: str = "Breaking changes",
    other_title: str = "",
) -> BucketedCommits:
    """Group conventional commits by changelog section.

    Used by sectioned renderers (Markdown CHANGELOG.md). Same arguments
    as :func:`filter_commits`: ``breaking_title="" `` disables the
    breaking bucket (breaking commits then fall through to whichever
    section claims their type), ``other_title=""`` drops unmatched
    commits entirely.

    ``bump_rules`` (if passed) bridges the bump configuration with the
    rendered sections. Any commit type with a non-``"none"`` rule is
    considered "interesting": if no explicit section claims it, an
    auto-bucket titled ``type.title()`` is created (e.g. ``docs:`` →
    ``"Docs"`` section). Auto-buckets render *after* the explicitly
    declared sections, in alphabetical order for determinism.
    """
    sections = list(sections) if sections is not None else _default_changelog_sections()
    relevant = [c for c in commits if c.is_conventional]

    breaking: list[Commit] = []
    if breaking_title:
        breaking = [c for c in relevant if c.breaking]
    breaking_set = {id(c) for c in breaking}

    by_section: dict[str, list[Commit]] = {}
    for section in sections:
        type_set = {t.lower() for t in section.types}
        items = [
            c for c in relevant
            if id(c) not in breaking_set and c.type.lower() in type_set
        ]
        if items:
            by_section[section.title] = items

    section_claimed = {t.lower() for s in sections for t in s.types}

    # Auto-buckets for types declared in bump_rules but not claimed by
    # any explicit section. Sorted for stable output.
    rule_claimed: set[str] = set()
    if bump_rules:
        rule_claimed = {
            t.lower()
            for t, kind in bump_rules.items()
            if kind != "none"
        }
        for type_name in sorted(rule_claimed - section_claimed):
            items = [
                c for c in relevant
                if id(c) not in breaking_set and c.type.lower() == type_name
            ]
            if items:
                by_section[type_name.title()] = items

    leftovers: list[Commit] = []
    if other_title:
        all_claimed = section_claimed | rule_claimed
        leftovers = [
            c for c in relevant
            if id(c) not in breaking_set and c.type.lower() not in all_claimed
        ]

    return BucketedCommits(
        breaking=breaking,
        by_section=by_section,
        leftovers=leftovers,
    )


def filter_commits(
    commits: Iterable[Commit],
    *,
    sections: Sequence[ChangelogSection] | None = None,
    bump_rules: Mapping[str, BumpRule] | None = None,
    breaking_title: str = "Breaking changes",
    other_title: str = "",
) -> list[Commit]:
    """Flat list of commits passing the section filter, in input order.

    Used by renderers that don't section their output (Debian stanzas
    list bullets in original commit order). Equivalent to "any commit
    that ``bucket_commits`` would have placed somewhere", expressed as
    a single list.

    Same ``bump_rules`` semantics as :func:`bucket_commits`: a type
    with a non-``"none"`` rule is kept even when no explicit section
    claims it.
    """
    sections = list(sections) if sections is not None else _default_changelog_sections()
    section_types = {t.lower() for s in sections for t in s.types}
    rule_types = {
        t.lower() for t, kind in (bump_rules or {}).items() if kind != "none"
    }
    keep = section_types | rule_types
    keep_breaking = bool(breaking_title)
    keep_leftovers = bool(other_title)
    return [
        c for c in commits
        if c.is_conventional
        and (
            (keep_breaking and c.breaking)
            or c.type.lower() in keep
            or keep_leftovers
        )
    ]
