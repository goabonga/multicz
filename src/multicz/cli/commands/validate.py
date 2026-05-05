# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz validate`` - run config + repo sanity checks."""

from __future__ import annotations

import typer

from ...validation import validate as run_validation
from .. import app, presenters
from .._shared import _load


@app.command(name="validate")
def validate_cmd(
    strict: bool = typer.Option(
        False, "--strict",
        help="Exit non-zero on warnings too (CI gate).",
    ),
    output: str = typer.Option(
        "text", "--output", "-o", help="text | json",
    ),
) -> None:
    """Run every config + repo sanity check and report the findings.

    Checks performed:

    \b
    - bump_files exist on disk
    - components don't claim overlapping paths (first-match-wins is
      explicit, not silent)
    - mirror targets are owned by another component (otherwise no
      cascade fires) and don't loop back to the same component
    - declared triggers form no cycle
    - mirror cascades form no cycle
    - declared changelog paths are reachable
    - the planner can resolve the current version of every component
    - debian/changelog files (when format='debian') parse correctly

    Exit code:

    \b
    0  no errors (warnings/info don't fail unless --strict)
    1  at least one error
    2  --strict and at least one warning
    """
    repo, config = _load()
    findings = run_validation(repo, config)
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    infos = [f for f in findings if f.level == "info"]

    presenters.render_validate(findings, errors, warnings, infos, output=output)

    if errors:
        raise typer.Exit(code=1)
    if strict and warnings:
        raise typer.Exit(code=2)
