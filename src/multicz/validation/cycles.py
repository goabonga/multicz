# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Checks: detect cycles in the trigger and mirror graphs."""

from __future__ import annotations

from collections.abc import Iterator

from ._base import Finding, ValidationContext
from ._cycle import _find_cycle


class TriggerCycleCheck:
    name = "trigger_cycle"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        config = ctx.config
        # Edge: upstream -> downstream (downstream lists upstream in triggers)
        graph: dict[str, list[str]] = {n: [] for n in config.components}
        for name, comp in config.components.items():
            for upstream in comp.depends_on:
                if upstream in graph:
                    graph[upstream].append(name)

        cycle = _find_cycle(graph)
        if cycle is not None:
            yield Finding(
                level="error",
                check="trigger_cycle",
                component=None,
                message=f"trigger cycle: {' -> '.join([*cycle, cycle[0]])}",
            )


class MirrorCycleCheck:
    name = "mirror_cycle"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        config = ctx.config
        matcher = ctx.matcher
        # Edge: A -> B when A's mirror writes into a path owned by B
        graph: dict[str, list[str]] = {n: [] for n in config.components}
        for name, comp in config.components.items():
            for mirror in comp.mirrors:
                target = matcher.match(str(mirror.file))
                if target is not None and target != name and target not in graph[name]:
                    graph[name].append(target)

        cycle = _find_cycle(graph)
        if cycle is not None:
            yield Finding(
                level="error",
                check="mirror_cycle",
                component=None,
                message=f"mirror cascade cycle: {' -> '.join([*cycle, cycle[0]])}",
            )
