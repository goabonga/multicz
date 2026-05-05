# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz explain`` - detailed reasons for a component's planned bump."""

from __future__ import annotations

import typer

from ...planner import CommitReason, MirrorReason, TriggerReason
from .. import app, console, err
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
    if bump is None:
        console.print(
            f"[bold]{component}[/]: [dim]no bump pending - "
            "no relevant commits since the last tag[/]"
        )
        return

    console.print(f"[bold]Component:[/] {component}")
    console.print(f"  Current version: {bump.current}")
    console.print(
        f"  Next version:    {bump.next} [cyan]({bump.kind})[/]"
    )
    if bump.pre:
        console.print(f"  Pre-release:     {bump.pre}")
    if bump.finalize:
        console.print("  Finalize:        yes")
    console.print()
    console.print("[bold]Reasons:[/]")
    for index, reason in enumerate(bump.reasons, start=1):
        if isinstance(reason, CommitReason):
            console.print(f"  {index}. {reason.summary()}")
            console.print(f"      SHA:   {reason.sha}")
            scope = f"({reason.scope})" if reason.scope else ""
            console.print(f"      Type:  {reason.type}{scope} → {reason.bump_kind}")
            if reason.original_kind is not None:
                console.print(
                    f"      [yellow]Demoted from {reason.original_kind} "
                    "(bump_policy='scoped', different scope)[/]"
                )
            if reason.breaking:
                console.print("      Breaking: yes")
            console.print("      Files matched in this component:")
            for path in reason.files:
                console.print(f"        - {path}")
        elif isinstance(reason, TriggerReason):
            console.print(f"  {index}. {reason.summary()}")
            console.print(f"      Upstream:      {reason.upstream}")
            console.print(f"      Upstream kind: {reason.upstream_kind}")
        elif isinstance(reason, MirrorReason):
            console.print(f"  {index}. {reason.summary()}")
            console.print(f"      Upstream: {reason.upstream}")
            target = reason.file
            if reason.key:
                target += f":{reason.key}"
            console.print(f"      Wrote:    {target}")
        else:  # ManualReason
            console.print(f"  {index}. {reason.summary()}")
