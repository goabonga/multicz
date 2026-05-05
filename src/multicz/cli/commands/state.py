# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz state`` - inspect the optional state file."""

from __future__ import annotations

import typer

from ...state import load_state
from .. import app, err, presenters
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
        presenters.render_state_missing(
            str(config.project.state_file), output=output
        )
        return

    presenters.render_state(state_obj, str(config.project.state_file), output=output)
