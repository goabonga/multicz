# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz get`` - read the current value of a component's version."""

from __future__ import annotations

import typer

from ...formats import read_value
from .. import app, err
from .._shared import _load


@app.command(name="get")
def get_value(target: str = typer.Argument(..., help="component[.field]")) -> None:
    """Read the current value of a component's version (or mirrored field).

    Examples:

    \b
    multicz get api                # version from the first bump_file
    multicz get api.image_tag      # not yet implemented (reserved)
    """
    repo, config = _load()
    name, _, field = target.partition(".")
    if name not in config.components:
        err.print(f"[red]unknown component:[/] {name}")
        raise typer.Exit(code=1)
    comp = config.components[name]
    if not comp.bump_files:
        err.print(f"[red]component {name} has no bump_files[/]")
        raise typer.Exit(code=1)
    if field and field != "version":
        err.print(f"[red]unsupported field:[/] {field} (only 'version' is exposed today)")
        raise typer.Exit(code=1)
    primary = comp.bump_files[0]
    print(read_value(repo / primary.file, primary.key))
