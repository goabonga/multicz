# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Checks: changelog file paths and per-writer validation."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

from ._base import Finding, ValidationContext


class ChangelogPathCheck:
    name = "changelog_not_a_file"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        for name, comp in ctx.config.components.items():
            if comp.changelog is None:
                continue
            path = ctx.repo / comp.changelog
            if path.exists() and not path.is_file():
                yield Finding(
                    level="error",
                    check="changelog_not_a_file",
                    component=name,
                    message=(
                        f"changelog path {str(comp.changelog)!r} exists but is "
                        "not a regular file"
                    ),
                )


class WritersCheck:
    """Iterate every writer on every component and surface findings.

    Each writer's impl owns the actual checks (e.g. the debian-changelog
    impl parses the top stanza). This class is just the dispatch loop;
    it stamps the component name onto each finding so the report can
    show ``api: 'debian/changelog' top stanza is not a valid ...``.
    """

    name = "writers"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        from ..writers import impl_for

        for name, comp in ctx.config.components.items():
            for writer in comp.writers:
                impl = impl_for(writer)
                for finding in impl.validate(writer, ctx.repo):
                    yield replace(finding, component=name)
