# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz config`` - print the effective configuration.

After all defaults are applied, ``bump_rules`` is merged with
:data:`DEFAULT_BUMP_RULES`, and writers / mirrors are normalised, this
command dumps the *resolved* :class:`Config`. Useful for debugging
"why isn't my override taking effect?" without having to read the
schema or the source loader.

Output is TOML by default (round-trippable, matches what the user
wrote in ``multicz.toml``); JSON is also available for piping.
"""

from __future__ import annotations

import contextlib
from typing import Any

import tomlkit
import typer

from ...config import find_config
from .. import app, console, err
from .._shared import _load


def _strip_none(value: Any) -> Any:
    """Recursively drop ``None`` entries from dicts / lists.

    TOML can't represent null values, so the JSON-mode Pydantic dump
    has to be sanitised before tomlkit serialises it. Empty containers
    are kept (an empty list of components.X.mirrors is meaningful;
    ``maintainer = null`` isn't).
    """
    if isinstance(value, dict):
        return {
            k: _strip_none(v) for k, v in value.items() if v is not None
        }
    if isinstance(value, list):
        return [_strip_none(v) for v in value if v is not None]
    return value


@app.command(name="config")
def config_cmd(
    output: str = typer.Option(
        "toml", "--output", "-o",
        help="toml | json [default: toml]",
    ),
    component: str = typer.Option(
        None, "--component", "-c",
        help="Restrict output to a single component (plus the [project] table).",
    ),
    source: bool = typer.Option(
        False, "--source",
        help="Also print which file the config was loaded from (stderr).",
    ),
) -> None:
    """Print the effective multicz configuration.

    The output reflects what multicz actually parsed - every default
    applied, every alias normalised (e.g. project ``bump_rules`` merged
    with the conventional defaults). Pipe through ``jq`` (with
    ``--output json``) or read it directly when debugging an override
    that doesn't seem to take effect.

    Examples:

    \b
    multicz config                          # full config in TOML
    multicz config -c api                   # just the api component
    multicz config --output json | jq       # machine-readable
    """
    if output not in {"toml", "json"}:
        err.print(f"[red]unknown --output:[/] {output} (use 'toml' or 'json')")
        raise typer.Exit(code=1)

    repo, config = _load()

    if source:
        with contextlib.suppress(FileNotFoundError):
            err.print(f"[dim]config:[/] {find_config(repo)}")

    data = config.model_dump(mode="json")

    if component is not None:
        if component not in config.components:
            err.print(f"[red]unknown component:[/] {component}")
            raise typer.Exit(code=1)
        data = {
            "project": data["project"],
            "components": {component: data["components"][component]},
        }

    if output == "json":
        console.print_json(data=data)
        return

    # TOML output: tomlkit accepts the primitives-mode dict from
    # Pydantic, with ``None`` values stripped (TOML has no null).
    print(tomlkit.dumps(_strip_none(data)), end="")
