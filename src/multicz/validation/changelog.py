# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Checks: changelog file paths and Debian changelog parseability."""

from __future__ import annotations

from collections.abc import Iterator

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


class DebianChangelogCheck:
    name = "debian_changelog"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        from ..changelog import parse_top_stanza

        for name, comp in ctx.config.components.items():
            if comp.format != "debian" or comp.debian is None:
                continue
            path = ctx.repo / comp.debian.changelog
            if not path.exists():
                yield Finding(
                    level="info",
                    check="debian_changelog_missing",
                    component=name,
                    message=(
                        f"{str(comp.debian.changelog)!r} does not exist; "
                        "it will be created on the first bump"
                    ),
                )
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                yield Finding(
                    level="error",
                    check="debian_changelog_unreadable",
                    component=name,
                    message=f"could not read {str(comp.debian.changelog)!r}: {exc}",
                )
                continue
            if parse_top_stanza(text) is None:
                yield Finding(
                    level="error",
                    check="debian_changelog_unparseable",
                    component=name,
                    message=(
                        f"{str(comp.debian.changelog)!r} top stanza is not a "
                        "valid Debian changelog header"
                    ),
                )
