# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz plan`` - print the bump plan with reasons."""

from __future__ import annotations

from pathlib import Path

import typer

from .. import app, console, err
from .._shared import (
    _append_step_summary,
    _build_plan_or_exit,
    _load,
    _parse_force_specs,
)


def _append_plan_summary(path: Path, plan_obj, *, header: str) -> None:
    """Render a plan as a markdown summary and append it."""
    lines = [f"## {header}", ""]
    if not plan_obj:
        lines.append("_No bumps pending._")
        _append_step_summary(path, lines)
        return

    lines.extend([
        "| component | current | next | kind |",
        "|---|---|---|---|",
    ])
    for bump in plan_obj:
        lines.append(
            f"| `{bump.component}` | `{bump.current}` | "
            f"`{bump.next}` | {bump.kind} |"
        )
    lines.append("")
    for bump in plan_obj:
        lines.append(
            f"### `{bump.component}` - {bump.current} → {bump.next} "
            f"({bump.kind})"
        )
        lines.append("")
        for reason in bump.reasons:
            lines.append(f"- {reason.summary()}")
        lines.append("")
    _append_step_summary(path, lines)


@app.command(name="plan")
def plan_cmd(
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
    pre: str = typer.Option(
        None, "--pre",
        help="Plan as if invoked with `bump --pre <label>`.",
    ),
    finalize: bool = typer.Option(
        False, "--finalize",
        help="Plan as if invoked with `bump --finalize`.",
    ),
    since: str = typer.Option(
        None, "--since",
        help="Override the commit window: use this ref instead of each "
             "component's last tag. Useful for PR previews "
             "(--since origin/main) or migration scenarios "
             "(--since HEAD~10).",
    ),
    force: list[str] = typer.Option(
        None, "--force",
        help="Force-bump <name>:<kind>. Repeatable. Bypasses commit "
             "detection - use for manual rebuilds (CVE base image refresh, "
             "weekly artefact rebuild, …).",
    ),
    summary: Path = typer.Option(
        None, "--summary",
        help="Append a markdown summary of the plan to this file. "
             "Wire to $GITHUB_STEP_SUMMARY in CI to get a release "
             "preview at the top of the workflow run page.",
        dir_okay=False,
    ),
) -> None:
    """Print the bump plan: every component that would change, the new
    version, and the *reasons* (conventional commits, trigger cascades,
    mirror cascades) that drove each decision.

    The text form is grouped per component for visual scanning; the JSON
    form (``--output json``) is the machine-readable shape suited for CI:

    \b
    {
      "bumps": {
        "api": {
          "current": "1.2.0",
          "next": "1.3.0",
          "kind": "minor",
          "reasons": [
            {"kind": "commit", "sha": "abc1234", "type": "feat",
             "subject": "add login", "files": ["src/auth.py"], ...}
          ]
        }
      }
    }
    """
    if pre is not None and finalize:
        err.print("[red]--pre and --finalize are mutually exclusive[/]")
        raise typer.Exit(code=1)

    repo, config = _load()
    forced = _parse_force_specs(force, config) if force else {}
    plan_obj = _build_plan_or_exit(
        repo, config, pre=pre, finalize=finalize, since=since, force=forced or None
    )

    if summary is not None:
        _append_plan_summary(summary, plan_obj, header="Release plan")

    if output == "json":
        payload = {
            "schema_version": 1,
            "bumps": {
                bump.component: {
                    "current_version": str(bump.current),
                    "next_version": bump.next,
                    "kind": bump.kind,
                    "reasons": [r.to_dict() for r in bump.reasons],
                    "artifacts": [
                        a.render(component=bump.component, version=bump.next)
                        for a in config.components[bump.component].artifacts
                    ],
                }
                for bump in plan_obj
            },
        }
        console.print_json(data=payload)
        return

    if not plan_obj:
        console.print("[dim]no bumps pending[/]")
        return

    for bump in plan_obj:
        header = (
            f"[bold]{bump.component}[/]: "
            f"{bump.current} → {bump.next} "
            f"[cyan]({bump.kind})[/]"
        )
        console.print(header)
        for reason in bump.reasons:
            console.print(f"  • {reason.summary()}")
        console.print()
