# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz check`` - validate a commit message file."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from ...commits import DEFAULT_TYPES, validate_message
from .. import app, err


@app.command()
def check(
    file: str = typer.Argument(
        ..., help="Commit message file (use '-' to read from stdin).",
    ),
    types: list[str] = typer.Option(
        None, "--type",
        help="Restrict allowed commit types (repeatable). Defaults to the full set.",
    ),
) -> None:
    """Validate a commit message file against the conventional-commits regex.

    Designed for use as a ``commit-msg`` git hook:

    \b
    .git/hooks/commit-msg
    -----
    #!/bin/sh
    exec multicz check "$1"
    """
    if file == "-":
        message = sys.stdin.read()
    else:
        path = Path(file)
        if not path.is_file():
            err.print(f"[red]not a file:[/] {file}")
            raise typer.Exit(code=1)
        message = path.read_text(encoding="utf-8")

    allowed = tuple(types) if types else DEFAULT_TYPES
    error = validate_message(message, allowed_types=allowed)
    if error is not None:
        err.print(f"[red]invalid commit message:[/] {error}")
        first = next((line for line in message.splitlines() if line.strip()), "")
        if first:
            err.print(f"[dim]got:[/] {first}")
        raise typer.Exit(code=1)
