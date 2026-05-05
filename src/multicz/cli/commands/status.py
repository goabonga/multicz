# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz status`` - brief summary of pending bumps."""

from __future__ import annotations

import typer

from .. import app, presenters
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
    presenters.render_status_table(plan_obj)
