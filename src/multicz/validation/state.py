# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Check: compare the recorded state versus the in-tree bump_files."""

from __future__ import annotations

from collections.abc import Iterator

from ._base import Finding, ValidationContext


class StateDriftCheck:
    """Compare the recorded state versus the in-tree bump_files.

    Only fires when ``project.state_file`` is configured. Catches manual
    edits to ``pyproject.toml`` / ``Chart.yaml`` / ``package.json`` that
    bypass ``multicz bump`` and leave the state file behind.
    """

    name = "state_drift"

    def run(self, ctx: ValidationContext) -> Iterator[Finding]:
        config = ctx.config
        repo = ctx.repo
        if config.project.state_file is None:
            return
        from ..formats import FormatError, read_value
        from ..state import load_state

        state_path = repo / config.project.state_file
        state = load_state(state_path)
        if state is None:
            return  # not yet bumped; nothing to compare

        for name, comp_state in state.components.items():
            comp = config.components.get(name)
            if comp is None:
                yield Finding(
                    level="warning",
                    check="state_unknown_component",
                    component=name,
                    message=(
                        f"state file references {name!r} but the component is "
                        "no longer declared in multicz.toml"
                    ),
                )
                continue
            if not comp.bump_files or comp.format == "debian":
                continue
            primary = comp.bump_files[0]
            try:
                current = read_value(repo / primary.file, primary.key)
            except (FormatError, OSError):
                continue
            if current != comp_state.version:
                yield Finding(
                    level="warning",
                    check="state_drift",
                    component=name,
                    message=(
                        f"state recorded version {comp_state.version!r} but "
                        f"{primary.file.as_posix()} now reads {current!r} - "
                        "someone may have edited the file outside multicz bump"
                    ),
                )
