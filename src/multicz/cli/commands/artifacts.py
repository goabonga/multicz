# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz artifacts`` - render the artifact refs a component would publish."""

from __future__ import annotations

import typer

from .. import app, console, err
from .._shared import _load


@app.command()
def artifacts(
    component: str = typer.Argument(
        None,
        help="Component to render artifacts for. Required unless --all is set.",
    ),
    all_: bool = typer.Option(
        False, "--all",
        help="Render artifacts for every component.",
    ),
    version_override: str = typer.Option(
        None, "--version",
        help="Render with this explicit version instead of the current one.",
    ),
    output: str = typer.Option(
        "text", "--output", "-o", help="text | json",
    ),
) -> None:
    """List the artifacts a component (or all components) would publish.

    multicz does not build or push artifacts itself; this command surfaces
    the rendered refs from the [components.<name>.artifacts] declarations
    so CI scripts can drive `docker build/push`, `helm package/push`, etc.

    \b
    Default version: the current version (from the latest tag, or the
    primary bump_file). Pass --version X to render against an explicit
    target (typically what `multicz bump --output json` would produce).
    """
    if component is None and not all_:
        err.print("[red]specify a component or --all[/]")
        raise typer.Exit(code=1)
    if component is not None and all_:
        err.print("[red]--all is exclusive with a component name[/]")
        raise typer.Exit(code=1)

    repo, config = _load()
    targets = list(config.components) if all_ else [component]
    payload: dict[str, dict] = {}
    for name in targets:
        if name not in config.components:
            err.print(f"[red]unknown component:[/] {name}")
            raise typer.Exit(code=1)
        comp = config.components[name]
        if version_override is not None:
            version = version_override
        else:
            from ...planner import _current_version
            version = str(_current_version(repo, config, name))
        rendered = [
            a.render(component=name, version=version) for a in comp.artifacts
        ]
        payload[name] = {"version": version, "artifacts": rendered}

    if output == "json":
        console.print_json(data=payload)
        return

    for name, data in payload.items():
        if not data["artifacts"]:
            console.print(f"[dim]{name}: no artifacts declared[/]")
            continue
        console.print(f"[bold]{name}[/] ({data['version']})")
        for a in data["artifacts"]:
            console.print(f"  [{a['type']}] {a['ref']}")
