# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Plugin-contributed sections wired into the changelog renderer."""

from __future__ import annotations

from multicz.changelog.markdown import render_body, render_section
from multicz.commits import parse_commit
from multicz.plugins import ChangelogEntry


def test_plugin_section_appended_below_commit_sections():
    """A plugin entry with a brand-new section name lands as its own
    H3 below the existing commit-driven sections."""
    commits = [parse_commit("a", "feat: x", ())]
    out = render_body(
        commits,
        plugin_sections=[
            ChangelogEntry(
                section="Deprecated",
                component="api",
                lines=("foo:1 marked since 1.0, remove in 3.0",),
            )
        ],
    )
    assert "### Features" in out
    assert "### Deprecated" in out
    assert out.index("### Features") < out.index("### Deprecated")
    assert "foo:1 marked since 1.0, remove in 3.0" in out


def test_plugin_section_merges_into_existing_title():
    """If a plugin emits an entry whose section matches an existing
    commit section (e.g. "Features"), the lines are appended to that
    section's bucket rather than creating a duplicate H3."""
    commits = [parse_commit("a", "feat: x", ())]
    out = render_body(
        commits,
        plugin_sections=[
            ChangelogEntry(section="Features", component="api", lines=("extra plugin line",))
        ],
    )
    # Single ### Features heading.
    assert out.count("### Features") == 1
    assert "x (`a`)" in out
    assert "extra plugin line" in out


def test_plugin_section_alone_suppresses_no_notable_changes():
    """A release with NO commits + cascades but plugin entries must NOT
    render `_No notable changes._` — the plugin output IS the content."""
    out = render_body(
        [],
        plugin_sections=[
            ChangelogEntry(section="Removed", component="api", lines=("dropped X",))
        ],
    )
    assert "_No notable changes._" not in out
    assert "### Removed" in out
    assert "dropped X" in out


def test_plugin_section_with_empty_lines_is_ignored():
    """A ``ChangelogEntry`` with no lines must not create an empty H3."""
    out = render_body(
        [parse_commit("a", "feat: x", ())],
        plugin_sections=[ChangelogEntry(section="Deprecated", component="api", lines=())],
    )
    assert "### Deprecated" not in out


def test_render_section_passes_plugin_sections_through():
    """The high-level ``render_section`` wrapper must forward
    ``plugin_sections`` to ``render_body``."""
    out = render_section(
        version="1.0.0",
        commits=[parse_commit("a", "feat: x", ())],
        plugin_sections=[
            ChangelogEntry(section="Removed", component="api", lines=("OldAPI",))
        ],
    )
    assert "## [1.0.0]" in out
    assert "### Removed" in out
    assert "OldAPI" in out


def test_multiple_plugin_entries_same_section_concatenate():
    """Two plugin entries for the same section name merge their lines."""
    out = render_body(
        [],
        plugin_sections=[
            ChangelogEntry(section="Deprecated", component="api", lines=("a",)),
            ChangelogEntry(section="Deprecated", component="api", lines=("b", "c")),
        ],
    )
    assert out.count("### Deprecated") == 1
    assert "- a" in out
    assert "- b" in out
    assert "- c" in out
