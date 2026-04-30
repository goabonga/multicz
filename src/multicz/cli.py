"""Command line interface for multicz."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .commits import commits_since, latest_tag, tag_prefix
from .components import ComponentMatcher
from .config import CONFIG_FILENAME, find_config, load_config
from .planner import build_plan
from .writers import read_value, write_value

app = typer.Typer(
    name="multicz",
    help="Multi-component versioning for monorepos.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)


_DEFAULT_CONFIG = """\
# multicz.toml — multi-component versioning config
# https://github.com/goabonga/multicz

[project]
commit_convention = "conventional"
tag_format = "{component}-v{version}"
initial_version = "0.1.0"

[components.api]
paths = ["src/**", "pyproject.toml", "tests/**", "Dockerfile", ".dockerignore"]
bump_files = [
  { file = "pyproject.toml", key = "project.version" },
]
mirrors = [
  { file = "charts/myapp/Chart.yaml", key = "appVersion" },
]

[components.chart]
paths = ["charts/myapp/**"]
bump_files = [
  { file = "charts/myapp/Chart.yaml", key = "version" },
]
"""


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"multicz {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show the multicz version and exit.",
    ),
) -> None:
    """Multi-component versioning for monorepos."""


@app.command()
def init(
    path: Path = typer.Option(
        None, "--path", "-p", help="Directory to write multicz.toml into.",
        file_okay=False, dir_okay=True, resolve_path=True,
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing config."),
) -> None:
    """Bootstrap a starter multicz.toml in the given directory."""
    target = (path or Path.cwd()) / CONFIG_FILENAME
    if target.exists() and not force:
        err.print(f"[red]{target} already exists.[/] Use --force to overwrite.")
        raise typer.Exit(code=1)
    target.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    console.print(f"[green]wrote[/] {target}")


def _load() -> tuple[Path, object]:
    try:
        config_path = find_config()
    except FileNotFoundError as exc:
        err.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc
    return config_path.parent, load_config(config_path)


@app.command()
def status() -> None:
    """Show which components would be bumped if you ran ``bump`` now."""
    repo, config = _load()
    plan = build_plan(repo, config)
    if not plan:
        console.print("[dim]no bumps pending[/]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("component")
    table.add_column("current")
    table.add_column("→")
    table.add_column("next")
    table.add_column("kind")
    table.add_column("reasons", overflow="fold")
    for bump in plan:
        table.add_row(
            bump.component,
            str(bump.current),
            "→",
            str(bump.next),
            bump.kind,
            "\n".join(bump.reasons),
        )
    console.print(table)


@app.command()
def bump(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Plan only, do not write."),
    component: list[str] = typer.Option(
        None, "--component", "-c", help="Restrict to these components (repeatable).",
    ),
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """Compute and apply the bump plan to all configured files."""
    repo, config = _load()
    plan = build_plan(repo, config)

    if component:
        plan.bumps = {n: b for n, b in plan.bumps.items() if n in set(component)}

    if not plan:
        if output == "json":
            console.print_json(data={"bumps": {}})
        else:
            console.print("[dim]no bumps pending[/]")
        return

    applied: dict[str, dict[str, str]] = {}
    for planned in plan:
        comp = config.components[planned.component]
        new_version = str(planned.next)
        targets: list[tuple[Path, str | None]] = []
        for bump_file in comp.bump_files:
            targets.append((repo / bump_file.file, bump_file.key))
        for mirror in comp.mirrors:
            targets.append((repo / mirror.file, mirror.key))

        for file, key in targets:
            if not dry_run:
                write_value(file, key, new_version)
        applied[planned.component] = {
            "current": str(planned.current),
            "next": new_version,
            "kind": planned.kind,
        }

    if output == "json":
        console.print_json(data={"bumps": applied, "dry_run": dry_run})
        return

    verb = "would bump" if dry_run else "bumped"
    for name, info in applied.items():
        console.print(
            f"[green]{verb}[/] [bold]{name}[/] {info['current']} → {info['next']} "
            f"([cyan]{info['kind']}[/])"
        )


@app.command(name="get")
def get_value(target: str = typer.Argument(..., help="component[.field]")) -> None:
    """Read the current value of a component's version (or mirrored field).

    Examples:

    \b
    multicz get api                # version from the first bump_file
    multicz get api.image_tag      # not yet implemented (reserved)
    """
    repo, config = _load()
    name, _, field = target.partition(".")
    if name not in config.components:
        err.print(f"[red]unknown component:[/] {name}")
        raise typer.Exit(code=1)
    comp = config.components[name]
    if not comp.bump_files:
        err.print(f"[red]component {name} has no bump_files[/]")
        raise typer.Exit(code=1)
    if field and field != "version":
        err.print(f"[red]unsupported field:[/] {field} (only 'version' is exposed today)")
        raise typer.Exit(code=1)
    primary = comp.bump_files[0]
    print(read_value(repo / primary.file, primary.key))


@app.command()
def changelog(
    component: str = typer.Option(None, "--component", "-c"),
) -> None:
    """Print a per-component log of conventional commits since the last tag."""
    repo, config = _load()
    matcher = ComponentMatcher(config.components)
    names = [component] if component else list(config.components)
    for name in names:
        if name not in config.components:
            err.print(f"[red]unknown component:[/] {name}")
            raise typer.Exit(code=1)
        prefix = tag_prefix(config.project.tag_format, name)
        since = latest_tag(repo, prefix)
        header = f"## {name}"
        if since:
            header += f"  (since {since})"
        console.print(f"\n[bold]{header}[/]")
        relevant = [
            c
            for c in commits_since(repo, since)
            if c.is_conventional and any(matcher.match(f) == name for f in c.files)
        ]
        if not relevant:
            console.print("  [dim]no changes[/]")
            continue
        for commit in relevant:
            scope = f"({commit.scope})" if commit.scope else ""
            bang = "!" if commit.breaking else ""
            console.print(
                f"  - {commit.type}{scope}{bang}: {commit.subject}"
                f"  [dim]({commit.sha[:7]})[/]"
            )


if __name__ == "__main__":  # pragma: no cover
    app()
