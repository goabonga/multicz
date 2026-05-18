# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz status`` - brief summary of pending bumps."""

from __future__ import annotations

import typer

from ...plugins import run_post_plan, run_status_lines
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

    # Surface plugin violations + advice so `status` doubles as a
    # "what would break if I ran bump right now" probe.
    violations = run_post_plan(config, repo, plan_obj)
    if violations:
        presenters.render_plugin_violations(violations, output="text")
    advice = run_status_lines(config, repo, plan_obj)
    if advice:
        presenters.render_plugin_advice(advice, output="text")
