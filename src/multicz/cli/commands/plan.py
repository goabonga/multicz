# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz plan`` - print the bump plan with reasons."""

from __future__ import annotations

from pathlib import Path

import typer

from ...plugins import run_post_plan, run_status_lines
from .. import app, err, presenters
from .._shared import (
    _build_plan_or_exit,
    _load,
    _parse_force_specs,
)


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
        presenters.append_plan_summary(summary, plan_obj, header="Release plan")

    presenters.render_plan(plan_obj, config, output=output)

    # Preview the post_plan hook so users see violations BEFORE running
    # `multicz bump` — same contract as the real gate, but never aborts.
    violations = run_post_plan(config, repo, plan_obj)
    if violations:
        presenters.render_plugin_violations(violations, output=output)

    # status_lines surface actionable advice from each plugin
    # (e.g. "remove deprecation X before bumping to 3.0").
    advice = run_status_lines(config, repo, plan_obj)
    if advice:
        presenters.render_plugin_advice(advice, output=output)
