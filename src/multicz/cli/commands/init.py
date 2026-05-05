# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz init`` - generate a multicz.toml tailored to the working tree."""

from __future__ import annotations

from pathlib import Path

import typer

from ...config import CONFIG_FILENAME, Component
from ...discovery import discover_components, render_config
from .. import app, console, err

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
        if output == "json":
            payload = {
                name: {
                    "paths": list(c.paths),
                    "format": c.format,
                    "bump_files": [
                        {"file": str(b.file), "key": b.key}
                        for b in c.bump_files
                    ],
                    "mirrors": [
                        {"file": str(m.file), "key": m.key}
                        for m in c.mirrors
                    ],
                    "changelog": str(c.changelog) if c.changelog else None,
                }
                for name, c in components.items()
            }
            console.print_json(data=payload)
            return
        console.print(f"[bold]Detected {len(components)} component(s):[/]")
        for name, comp in components.items():
            primary = comp.bump_files[0].file if comp.bump_files else None
            line = f"  • [bold]{name}[/]"
            if primary is not None:
                line += f" [dim]({primary.as_posix()})[/]"
            elif comp.format == "debian":
                line += " [dim](debian/changelog)[/]"
            else:
                line += " [dim](tag-driven)[/]"
            if comp.format != "default":
                line += f" [yellow]format={comp.format}[/]"
            if comp.mirrors:
                targets = ", ".join(
                    f"{m.file.as_posix()}:{m.key}" if m.key else m.file.as_posix()
                    for m in comp.mirrors
                )
                line += f"\n      mirrors → {targets}"
            console.print(line)
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
    console.print(f"[green]wrote[/] {target}{' [dim](bare stub)[/]' if bare else ''}")
    if components is not None:
        console.print(f"[dim]detected:[/] {', '.join(components)}")
