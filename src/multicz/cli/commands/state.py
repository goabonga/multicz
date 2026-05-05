# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz state`` - inspect the optional state file."""

from __future__ import annotations

import typer

from ...state import load_state
from .. import app, console, err
from .._shared import _load


@app.command()
def state(
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """Inspect the optional state file written after each successful bump.

    The state file is opt-in via ``[project].state_file = "..."``. It
    records the per-component version, the expected tag name (when
    ``--tag`` was used at bump time), the SHA the bump was computed
    against, and a UTC timestamp.
    """
    repo, config = _load()
    if config.project.state_file is None:
        err.print(
            "[red]no state_file configured[/] - set "
            "[bold][project].state_file[/] in multicz.toml"
        )
        raise typer.Exit(code=1)

    path = repo / config.project.state_file
    state_obj = load_state(path)
    if state_obj is None:
        if output == "json":
            console.print_json(data=None)
        else:
            console.print(
                f"[dim]{config.project.state_file} not yet written[/]"
            )
        return

    if output == "json":
        console.print_json(data=state_obj.to_dict())
        return

    console.print(
        f"[bold]state[/] {config.project.state_file} "
        f"(schema v{state_obj.version})"
    )
    console.print(f"  git_head:  {state_obj.git_head_short or state_obj.git_head}")
    console.print(f"  timestamp: {state_obj.timestamp}")
    for name, comp in state_obj.components.items():
        line = f"  [bold]{name}[/]: {comp.version}"
        if comp.tag:
            line += f"  [dim]({comp.tag})[/]"
        console.print(line)
