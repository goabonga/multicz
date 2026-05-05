# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz init`` - generate a multicz.toml tailored to the working tree."""

from __future__ import annotations

from pathlib import Path

import typer

from ...config import CONFIG_FILENAME, Component
from ...discovery import discover_components, render_config
from .. import app, err, presenters

_BARE_CONFIG = """\
# multicz.toml - generic stub. Edit paths and bump_files to match your repo.
# Run `multicz init` (without --bare) to scan the working tree and generate
# a config tailored to the manifests it actually contains.

[project]
commit_convention = "conventional"
tag_format = "{component}-v{version}"
initial_version = "0.1.0"

[components.app]
paths = ["src/**", "pyproject.toml"]
bump_files = [
  { file = "pyproject.toml", key = "project.version" },
]
changelog = "CHANGELOG.md"
"""


@app.command()
def init(
    path: Path = typer.Option(
        None, "--path", "-p", help="Directory to write multicz.toml into.",
        file_okay=False, dir_okay=True, resolve_path=True,
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing config."),
    bare: bool = typer.Option(
        False, "--bare",
        help="Skip auto-discovery and write a generic single-component stub.",
    ),
    print_only: bool = typer.Option(
        False, "--print",
        help="Print the rendered config to stdout instead of writing a file. "
             "Composes with --bare. Useful for `multicz init --print > file`.",
    ),
    detect: bool = typer.Option(
        False, "--detect",
        help="Scan and summarise detected components without rendering the "
             "full TOML. Use --output json for machine-readable output.",
    ),
    output: str = typer.Option(
        "text", "--output", "-o",
        help="text | json (only meaningful with --detect)",
    ),
    skip: str = typer.Option(
        "", "--skip",
        help="Comma-separated list of discovery strategies to disable "
             "(e.g. 'helm,gradle'). Recognised names: python, cargo, "
             "gradle, go, helm.",
    ),
) -> None:
    """Generate a multicz.toml tailored to the working tree.

    By default the working tree is scanned for ``pyproject.toml``,
    ``charts/*/Chart.yaml``, ``package.json``, ``Cargo.toml``, ``go.mod``,
    ``gradle.properties`` and ``debian/changelog``; one component is
    emitted per detected manifest. ``--bare`` writes a generic
    single-component stub instead - useful when bootstrapping a brand
    new repo.

    \b
    Three output modes:
      (default)   write multicz.toml to disk
      --print     render to stdout (composes with --bare)
      --detect    summary of what would be detected, no full config rendered
    """
    if detect and bare:
        err.print("[red]--detect cannot be combined with --bare[/]")
        raise typer.Exit(code=1)
    if detect and print_only:
        err.print("[red]--detect cannot be combined with --print[/]")
        raise typer.Exit(code=1)

    target_dir = path or Path.cwd()

    skip_set = {s.strip() for s in skip.split(",") if s.strip()}

    # Compute components (or skip when --bare)
    components: dict[str, Component] | None = None
    if not bare:
        components = discover_components(target_dir, skip=skip_set)
        if not components:
            err.print(
                "[yellow]no manifests detected[/] under "
                f"{target_dir} (looked for pyproject.toml, "
                "charts/*/Chart.yaml, package.json, Cargo.toml, go.mod, "
                "gradle.properties, debian/changelog). Use [bold]--bare[/] "
                "to write a generic stub."
            )
            raise typer.Exit(code=1)

    if detect:
        # `components` is non-None here because --detect+--bare is rejected
        assert components is not None
        presenters.render_init_detect(components, output=output)
        return

    content = _BARE_CONFIG if bare else render_config(components)  # type: ignore[arg-type]

    if print_only:
        # `print` (vs console.print) avoids any rich markup so the output
        # is byte-for-byte usable for redirection.
        print(content, end="")
        return

    target = target_dir / CONFIG_FILENAME
    if target.exists() and not force:
        err.print(f"[red]{target} already exists.[/] Use --force to overwrite.")
        raise typer.Exit(code=1)
    target.write_text(content, encoding="utf-8")
    presenters.render_init_wrote(target, bare=bare, components=components)
