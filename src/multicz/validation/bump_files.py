# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Check: every declared bump_file path exists in the repo."""

from __future__ import annotations

from collections.abc import Iterator

from ._base import Finding, ValidationContext


class BumpFilesExistCheck:
    name = "bump_files_exist"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        for name, comp in ctx.config.components.items():
            for fk in comp.bump_files:
                path = ctx.repo / fk.file
                if not path.is_file():
                    yield Finding(
                        level="error",
                        check="bump_files_exist",
                        component=name,
                        message=f"bump_file {fk.file.as_posix()!r} does not exist",
                    )
