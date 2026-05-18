# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

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
    """List every plugin discovered via the ``multicz.plugins`` entry-point
    group, along with its enabled/disabled state and the
    ``[plugins.<name>]`` config table the plugin will read.

    Useful to:

    * verify a third-party plugin is being picked up after install
    * confirm a plugin is disabled via ``enabled = false``
    * see at a glance which plugins gate the next ``multicz bump``

    \b
    Example:

    \b
        $ multicz plugins
        Plugin       Status     Config section
        deprecation  enabled    [plugins.deprecation]
                                  mode = "error"
                                  scan = ["packages/api/src/**/*.py"]
    """
    _, config = _load()
    plugins = list(DEFAULT_REGISTRY)
    plugins_table: dict[str, dict] = getattr(config, "plugins", {}) or {}
    presenters.render_plugins_list(plugins, plugins_table, output=output)
