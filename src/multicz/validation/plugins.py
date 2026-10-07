# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Check: report what active plugins find wrong through their validate hook."""

from __future__ import annotations

from collections.abc import Iterator

from ..plugins import PluginRegistry, run_validate
from ._base import Finding, ValidationContext


class PluginValidationCheck:
    """Turn every active plugin's :meth:`~multicz.plugins.Plugin.validate`
    violations into findings, at the same level.

    A plugin's findings use the ``plugin:<name>`` check identifier, so the
    report says which plugin raised them.
    """

    name = "plugins"

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self._registry = registry

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        for violation in run_validate(ctx.config, ctx.repo, registry=self._registry):
            where = ""
            if violation.file is not None:
                line = f":{violation.line}" if violation.line else ""
                where = f"{violation.file}{line}: "
            yield Finding(
                level=violation.severity.value,
                check=f"plugin:{violation.plugin}",
                component=violation.component,
                message=f"{where}{violation.message}",
            )
