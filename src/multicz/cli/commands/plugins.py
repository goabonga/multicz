# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz plugins`` - list discovered plugins and their config state."""

from __future__ import annotations

import typer

from ...plugins import DEFAULT_REGISTRY
from .. import app, presenters
from .._shared import _load


@app.command(name="plugins")
def plugins_cmd(
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """List every plugin discovered via the multicz.plugins entry-point
    group with its enabled/disabled state and config section.

    Useful to verify a third-party plugin is picked up after install,
    confirm one is disabled via ``enabled = false``, or see at a glance
    which plugins gate the next ``multicz bump``.
    """
    _, config = _load()
    plugins = list(DEFAULT_REGISTRY)
    plugins_table: dict[str, dict] = getattr(config, "plugins", {}) or {}
    presenters.render_plugins_list(plugins, plugins_table, output=output)
