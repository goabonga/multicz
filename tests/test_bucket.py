# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Tests for the pure commit bucketing logic shared by both changelog
renderers (markdown ``CHANGELOG.md`` and Debian ``debian/changelog``).

Each renderer's *format-specific* tests live in ``test_changelog.py``
(markdown) and ``test_debian.py`` (Debian); this file covers only the
bucket / filter primitives — what counts as breaking, which commits
land in which section bucket, what falls through to ``leftovers``.
"""

from multicz.changelog.bucket import (
    BucketedCommits,
    bucket_commits,
    filter_commits,
)
from multicz.commits import parse_commit
from multicz.config import ChangelogSection

DEFAULT_SECTIONS = [
    ChangelogSection(title="Features", types=["feat"]),
    ChangelogSection(title="Fixes", types=["fix"]),
    ChangelogSection(title="Performance", types=["perf"]),
]


# bucket_commits ---------------------------------------------------------


def test_bucket_groups_by_section_title_in_declared_order():
    commits = [
        parse_commit("a", "fix: a bug", ()),
        parse_commit("b", "feat: a feature", ()),
        parse_commit("c", "perf: faster", ()),
    ]
    b = bucket_commits(commits, sections=DEFAULT_SECTIONS)
    # Iteration order matches the order of `sections`.
    assert list(b.by_section.keys()) == ["Features", "Fixes", "Performance"]
    assert [c.subject for c in b.by_section["Features"]] == ["a feature"]
    assert [c.subject for c in b.by_section["Fixes"]] == ["a bug"]
    assert [c.subject for c in b.by_section["Performance"]] == ["faster"]


def test_bucket_extracts_breaking_commits_from_their_type_section():
    """A `feat!:` commit lands in the breaking bucket, not the Features
    bucket — so a renderer can place it in a dedicated section without
    double-counting."""
    commits = [
        parse_commit("a", "feat: regular", ()),
        parse_commit("b", "feat!: breaking", ()),
    ]
    b = bucket_commits(commits, sections=DEFAULT_SECTIONS)
    assert len(b.breaking) == 1
    assert b.breaking[0].subject == "breaking"
    assert [c.subject for c in b.by_section["Features"]] == ["regular"]


def test_bucket_drops_breaking_extraction_when_breaking_title_is_empty():
    """An empty `breaking_title` disables the breaking bucket — breaking
    commits then fall through to whichever section claims their type."""
    commits = [parse_commit("a", "feat!: breaking", ())]
    b = bucket_commits(commits, sections=DEFAULT_SECTIONS, breaking_title="")
    assert b.breaking == []
    assert [c.subject for c in b.by_section["Features"]] == ["breaking"]


def test_bucket_silently_drops_unmatched_types_by_default():
    """`other_title=""` (default) → chore/test/ci/docs commits are
    discarded outright. Keeps the changelog focused on user-visible
    changes."""
    commits = [
        parse_commit("a", "feat: a", ()),
        parse_commit("b", "chore: tidy", ()),
        parse_commit("c", "test: cover edge", ()),
    ]
    b = bucket_commits(commits, sections=DEFAULT_SECTIONS)
    assert b.leftovers == []
    assert [c.subject for c in b.by_section["Features"]] == ["a"]


def test_bucket_collects_unmatched_types_into_leftovers_when_other_title_set():
    commits = [
        parse_commit("a", "feat: a", ()),
        parse_commit("b", "chore: tidy", ()),
        parse_commit("c", "ci: bump runner", ()),
    ]
    b = bucket_commits(
        commits, sections=DEFAULT_SECTIONS, other_title="Misc",
    )
    assert [c.subject for c in b.leftovers] == ["tidy", "bump runner"]


def test_bucket_skips_non_conventional_commits():
    commits = [
        parse_commit("a", "feat: real", ()),
        parse_commit("b", "WIP fix something", ()),
        parse_commit("c", "fix: also real", ()),
    ]
    b = bucket_commits(commits, sections=DEFAULT_SECTIONS)
    # Non-conventional commit is gone from every bucket.
    assert "Features" in b.by_section
    assert "Fixes" in b.by_section
    assert all(
        "WIP" not in c.subject
        for s in b.by_section.values()
        for c in s
    )
    assert all("WIP" not in c.subject for c in b.breaking + b.leftovers)


def test_bucket_is_empty_when_no_commits_pass_filter():
    commits = [parse_commit("a", "chore: x", ())]
    b = bucket_commits(commits, sections=DEFAULT_SECTIONS)
    assert isinstance(b, BucketedCommits)
    assert b.is_empty


# filter_commits ---------------------------------------------------------


def test_filter_returns_flat_list_in_input_order():
    """Used by Debian renderer — preserves the original chronological
    order of commits, no per-section reorganization."""
    commits = [
        parse_commit("a", "feat: x", ()),
        parse_commit("b", "fix: y", ()),
        parse_commit("c", "feat: z", ()),
    ]
    out = filter_commits(commits, sections=DEFAULT_SECTIONS)
    assert [c.subject for c in out] == ["x", "y", "z"]


def test_filter_drops_chore_test_ci_by_default():
    commits = [
        parse_commit("a", "feat: keep", ()),
        parse_commit("b", "chore: drop", ()),
        parse_commit("c", "test: drop", ()),
        parse_commit("d", "fix: keep", ()),
    ]
    out = filter_commits(commits, sections=DEFAULT_SECTIONS)
    assert [c.subject for c in out] == ["keep", "keep"]


def test_filter_keeps_breaking_even_when_type_unknown():
    """A `chore!:` commit is breaking and must survive the filter even
    though `chore` matches no section."""
    commits = [
        parse_commit("a", "chore!: rip out legacy api", ()),
    ]
    out = filter_commits(commits, sections=DEFAULT_SECTIONS)
    assert len(out) == 1
    assert "legacy api" in out[0].subject


def test_filter_keeps_leftovers_when_other_title_set():
    commits = [
        parse_commit("a", "feat: x", ()),
        parse_commit("b", "chore: y", ()),
    ]
    out = filter_commits(
        commits, sections=DEFAULT_SECTIONS, other_title="Misc",
    )
    assert [c.subject for c in out] == ["x", "y"]


def test_filter_skips_non_conventional_commits():
    commits = [
        parse_commit("a", "feat: real", ()),
        parse_commit("b", "Random subject without type", ()),
    ]
    out = filter_commits(commits, sections=DEFAULT_SECTIONS)
    assert [c.subject for c in out] == ["real"]
