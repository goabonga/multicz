"""Command line interface for multicz."""

from __future__ import annotations

import subprocess
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


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
    )
    if result.returncode != 0:
        err.print(
            f"[red]git {' '.join(args)} failed ({result.returncode}):[/] "
            f"{result.stderr.strip()}"
        )
        raise typer.Exit(code=1)
    return result.stdout


def _release_commit_message(applied: dict[str, dict[str, str]]) -> str:
    parts = [f"{name} {info['current']} -> {info['next']}" for name, info in applied.items()]
    summary = ", ".join(parts)
    body_lines = [
        f"- {name}: {info['current']} -> {info['next']} ({info['kind']})"
        for name, info in applied.items()
    ]
    return f"chore(release): bump {summary}\n\n" + "\n".join(body_lines) + "\n"


@app.command()
def bump(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Plan only, do not write."),
    component: list[str] = typer.Option(
        None, "--component", "-c", help="Restrict to these components (repeatable).",
    ),
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
    commit: bool = typer.Option(
        False, "--commit", "-C",
        help="Stage written files and create a chore(release) commit.",
    ),
    tag: bool = typer.Option(
        False, "--tag", "-t",
        help="Create one annotated git tag per bumped component.",
    ),
    push: bool = typer.Option(
        False, "--push",
        help="Push the release commit and tags to origin (--follow-tags).",
    ),
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
    written: list[Path] = []
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
                if file not in written:
                    written.append(file)
        applied[planned.component] = {
            "current": str(planned.current),
            "next": new_version,
            "kind": planned.kind,
        }

    git_summary: dict[str, str | list[str]] = {}
    if not dry_run and commit and written:
        rel_paths = [str(p.relative_to(repo)) for p in written]
        _git(repo, "add", "--", *rel_paths)
        _git(repo, "commit", "-m", _release_commit_message(applied))
        sha = _git(repo, "rev-parse", "HEAD").strip()
        git_summary["commit"] = sha

    tags_created: list[str] = []
    if not dry_run and tag:
        for name, info in applied.items():
            tag_name = config.project.tag_format.format(
                component=name, version=info["next"]
            )
            _git(repo, "tag", "-m", f"{name} {info['next']}", tag_name)
            tags_created.append(tag_name)
        git_summary["tags"] = tags_created

    if not dry_run and push:
        _git(repo, "push", "--follow-tags")
        git_summary["pushed"] = "yes"

    if output == "json":
        console.print_json(data={"bumps": applied, "dry_run": dry_run, "git": git_summary})
        return

    verb = "would bump" if dry_run else "bumped"
    for name, info in applied.items():
        console.print(
            f"[green]{verb}[/] [bold]{name}[/] {info['current']} → {info['next']} "
            f"([cyan]{info['kind']}[/])"
        )
    if git_summary.get("commit"):
        console.print(f"[green]committed[/] {git_summary['commit'][:7]}")
    if tags_created:
        console.print(f"[green]tagged[/] {', '.join(tags_created)}")
    if git_summary.get("pushed"):
        console.print("[green]pushed[/]")


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


_MD_SECTIONS: list[tuple[str, set[str]]] = [
    ("Breaking changes", set()),  # special-cased: any commit with breaking=True
    ("Features", {"feat"}),
    ("Fixes", {"fix"}),
    ("Performance", {"perf"}),
    ("Other", set()),  # special-cased: anything else conventional
]


def _bucket(commit) -> str:
    if commit.breaking:
        return "Breaking changes"
    t = commit.type.lower()
    if t == "feat":
        return "Features"
    if t == "fix":
        return "Fixes"
    if t == "perf":
        return "Performance"
    return "Other"


@app.command()
def changelog(
    component: str = typer.Option(None, "--component", "-c"),
    output: str = typer.Option("text", "--output", "-o", help="text | md"),
) -> None:
    """Print a per-component log of conventional commits since the last tag."""
    repo, config = _load()
    matcher = ComponentMatcher(config.components)
    names = [component] if component else list(config.components)
    plan = build_plan(repo, config)

    md_lines: list[str] = []

    for name in names:
        if name not in config.components:
            err.print(f"[red]unknown component:[/] {name}")
            raise typer.Exit(code=1)
        prefix = tag_prefix(config.project.tag_format, name)
        since = latest_tag(repo, prefix)
        relevant = [
            c
            for c in commits_since(repo, since)
            if c.is_conventional and any(matcher.match(f) == name for f in c.files)
        ]

        if output == "md":
            planned = plan.bumps.get(name)
            heading = f"## {name}"
            if planned:
                heading += f" {planned.current} → {planned.next}"
            elif since:
                heading += f" (since {since})"
            md_lines.append(heading)
            md_lines.append("")
            if not relevant:
                md_lines.append("_No changes._")
                md_lines.append("")
                continue
            buckets: dict[str, list] = {title: [] for title, _ in _MD_SECTIONS}
            for commit in relevant:
                buckets[_bucket(commit)].append(commit)
            for section, _ in _MD_SECTIONS:
                items = buckets[section]
                if not items:
                    continue
                md_lines.append(f"### {section}")
                md_lines.append("")
                for commit in items:
                    scope = f"**{commit.scope}**: " if commit.scope else ""
                    md_lines.append(
                        f"- {scope}{commit.subject} (`{commit.sha[:7]}`)"
                    )
                md_lines.append("")
        else:
            header = f"## {name}"
            if since:
                header += f"  (since {since})"
            console.print(f"\n[bold]{header}[/]")
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

    if output == "md":
        # plain print so the output is pipeable into a CHANGELOG.md
        print("\n".join(md_lines).rstrip() + "\n")


if __name__ == "__main__":  # pragma: no cover
    app()
