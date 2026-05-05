# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz explain`` - detailed reasons for a component's planned bump."""

from __future__ import annotations

import typer

from .. import app, err, presenters
from .._shared import _build_plan_or_exit, _load


@app.command()
def explain(
    component: str = typer.Argument(..., help="Component to explain."),
    since: str = typer.Option(
        None, "--since",
        help="Override the commit window for this explanation.",
    ),
) -> None:
    """Detailed breakdown of why ``component`` is in the bump plan.

    Lists every reason with the structured fields: for commits, the SHA,
    type, scope, breaking marker, subject, and the changed files that
    actually matched the component's paths; for trigger/mirror cascades,
    the upstream component and the file/key that propagated.
    """
    repo, config = _load()
    if component not in config.components:
        err.print(f"[red]unknown component:[/] {component}")
        raise typer.Exit(code=1)

    plan_obj = _build_plan_or_exit(repo, config, since=since)
    bump = plan_obj.bumps.get(component)
    presenters.render_explain(component, bump)
