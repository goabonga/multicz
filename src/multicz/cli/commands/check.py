# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz check`` - validate a commit message file."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from ...commits import DEFAULT_TYPES, validate_message
from ...config import find_config, load_config
from .. import app, err


def _allowed_types_from_config() -> tuple[str, ...]:
    """Allowed conventional-commit types: union of the project's
    ``bump_rules`` keys and the conventional baseline. Falls back to
    :data:`DEFAULT_TYPES` if no config file is reachable or if loading
    fails for any reason (the commit-msg hook must never block on a
    config issue — it only validates the header shape)."""
    try:
        config = load_config(find_config(Path.cwd()))
    except (FileNotFoundError, ValueError):
        return DEFAULT_TYPES
    return tuple(sorted(set(DEFAULT_TYPES) | set(config.project.bump_rules)))


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

    allowed = tuple(types) if types else _allowed_types_from_config()
    error = validate_message(message, allowed_types=allowed)
    if error is not None:
        err.print(f"[red]invalid commit message:[/] {error}")
        first = next((line for line in message.splitlines() if line.strip()), "")
        if first:
            err.print(f"[dim]got:[/] {first}")
        raise typer.Exit(code=1)
