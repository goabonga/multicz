# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Check: classify mirror targets (unowned vs self-targeting)."""

from __future__ import annotations

from collections.abc import Iterator

from ._base import Finding, ValidationContext


class MirrorTargetsCheck:
    """Yield findings for mirror targets that are unowned or self-targeting.

    A single pass produces both ``mirror_target_unowned`` (info) and
    ``mirror_self_target`` (warning) findings.
    """

    name = "mirror_targets"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        for name, comp in ctx.config.components.items():
            for mirror in comp.mirrors:
                target = ctx.matcher.match(str(mirror.file))
                if target is None:
                    yield Finding(
                        level="info",
                        check="mirror_target_unowned",
                        component=name,
                        message=(
                            f"mirror target {str(mirror.file)!r} is not owned by "
                            "any component; the version is written but no cascade "
                            "fires"
                        ),
                    )
                elif target == name:
                    yield Finding(
                        level="warning",
                        check="mirror_self_target",
                        component=name,
                        message=(
                            f"mirror target {str(mirror.file)!r} resolves back to "
                            "this component; you probably want a bump_files entry "
                            "instead of a mirror"
                        ),
                    )
