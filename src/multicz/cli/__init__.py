# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Command line interface for multicz."""

from __future__ import annotations

# `subprocess` is re-exported at the package level because tests patch
# ``multicz.cli.subprocess.run`` (see tests/test_cli.py); since
# monkeypatch.setattr resolves the attribute path on the module, the
# package must expose the name.
import subprocess  # noqa: F401

import typer
from rich.console import Console

from .. import __version__

app = typer.Typer(
    name="multicz",
    help="Multi-component versioning for monorepos.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"multicz {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show the multicz version and exit.",
    ),
) -> None:
    """Multi-component versioning for monorepos."""


# Importing the command modules triggers their `@app.command()` decorators,
# which is what registers them on the Typer app above. Order is alphabetical
# only for readability; Typer doesn't care.
from .commands import (  # noqa: E402, F401
    artifacts,
    bump,
    changed,
    changelog,
    check,
    config,
    explain,
    get,
    init,
    plan,
    release_notes,
    state,
    status,
    validate,
)

if __name__ == "__main__":  # pragma: no cover
    app()
