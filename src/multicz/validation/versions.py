# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Check: every component's current version can be resolved."""

from __future__ import annotations

from collections.abc import Iterator

from ._base import Finding, ValidationContext


class CurrentVersionCheck:
    name = "version_unreadable"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        from ..planner import _current_version

        for name in ctx.config.components:
            try:
                _current_version(ctx.repo, ctx.config, name)
            except Exception as exc:
                yield Finding(
                    level="error",
                    check="version_unreadable",
                    component=name,
                    message=f"could not resolve current version: {exc}",
                )
