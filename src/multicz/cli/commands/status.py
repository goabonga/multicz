# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz status`` - brief summary of pending bumps."""

from __future__ import annotations

import typer
from rich.table import Table

from .. import app, console
from .._shared import _build_plan_or_exit, _load


@app.command()
def status(
    since: str = typer.Option(
        None, "--since",
        help="Override the commit window: use this ref instead of each "
             "component's last tag. Useful for PR previews "
             "(--since origin/main).",
    ),
) -> None:
    """Brief summary of pending bumps (alias of ``plan`` without reasons)."""
    repo, config = _load()
    plan_obj = _build_plan_or_exit(repo, config, since=since)
    if not plan_obj:
        console.print("[dim]no bumps pending[/]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("component")
    table.add_column("current")
    table.add_column("→")
    table.add_column("next")
    table.add_column("kind")
    table.add_column("reasons", overflow="fold")
    for bump in plan_obj:
        table.add_row(
            bump.component,
            str(bump.current),
            "→",
            str(bump.next),
            bump.kind,
            "\n".join(bump.reason_summaries()),
        )
    console.print(table)
