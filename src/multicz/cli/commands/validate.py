# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz validate`` - run config + repo sanity checks."""

from __future__ import annotations

import typer

from ...validation import validate as run_validation
from .. import app, console
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

    if output == "json":
        console.print_json(data={
            "findings": [f.to_dict() for f in findings],
            "summary": {
                "errors": len(errors),
                "warnings": len(warnings),
                "info": len(infos),
            },
        })
    else:
        if not findings:
            console.print("[green]✓ no issues found[/]")
        else:
            colors = {"error": "red", "warning": "yellow", "info": "blue"}
            tags = {"error": "✗", "warning": "!", "info": "i"}
            for finding in findings:
                color = colors[finding.level]
                tag = tags[finding.level]
                comp = (
                    f"[bold]{finding.component}[/]: "
                    if finding.component
                    else ""
                )
                console.print(
                    f"[{color}]{tag}[/] {comp}{finding.message}  "
                    f"[dim]({finding.check})[/]"
                )
            console.print()
            counts: list[str] = []
            if errors:
                counts.append(
                    f"[red]{len(errors)} error{'s' if len(errors) != 1 else ''}[/]"
                )
            if warnings:
                counts.append(
                    f"[yellow]{len(warnings)} "
                    f"warning{'s' if len(warnings) != 1 else ''}[/]"
                )
            if infos:
                counts.append(f"[blue]{len(infos)} info[/]")
            console.print(", ".join(counts))

    if errors:
        raise typer.Exit(code=1)
    if strict and warnings:
        raise typer.Exit(code=2)
