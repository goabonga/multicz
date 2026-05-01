"""Command line interface for multicz."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .changelog import render_body, update_changelog_file
from .commits import (
    DEFAULT_TYPES,
    commits_since,
    latest_stable_tag,
    latest_tag,
    tag_prefix,
    validate_message,
)
from .components import ComponentMatcher
from .config import CONFIG_FILENAME, find_config, load_config
from .debian import (
    drop_prerelease_stanzas,
    format_debian_version,
    prepend_stanza,
    render_stanza,
)
from .discovery import discover_components, render_config
from .planner import (
    CommitReason,
    MirrorReason,
    TriggerReason,
    build_plan,
)
from .writers import read_value, write_value

app = typer.Typer(
    name="multicz",
    help="Multi-component versioning for monorepos.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)


_BARE_CONFIG = """\
# multicz.toml — generic stub. Edit paths and bump_files to match your repo.
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
    bare: bool = typer.Option(
        False, "--bare",
        help="Skip auto-discovery and write a generic single-component stub.",
    ),
) -> None:
    """Generate a multicz.toml tailored to the working tree.

    By default the working tree is scanned for ``pyproject.toml``,
    ``charts/*/Chart.yaml`` and ``package.json``; one component is emitted per
    detected manifest. ``--bare`` writes a generic single-component stub
    instead — useful when bootstrapping a brand new repo.
    """
    target_dir = path or Path.cwd()
    target = target_dir / CONFIG_FILENAME
    if target.exists() and not force:
        err.print(f"[red]{target} already exists.[/] Use --force to overwrite.")
        raise typer.Exit(code=1)

    if bare:
        target.write_text(_BARE_CONFIG, encoding="utf-8")
        console.print(f"[green]wrote[/] {target} [dim](bare stub)[/]")
        return

    components = discover_components(target_dir)
    if not components:
        err.print(
            "[yellow]no manifests detected[/] under "
            f"{target_dir} (looked for pyproject.toml, charts/*/Chart.yaml, "
            "package.json). Use [bold]--bare[/] to write a generic stub."
        )
        raise typer.Exit(code=1)

    target.write_text(render_config(components), encoding="utf-8")
    console.print(f"[green]wrote[/] {target}")
    console.print(f"[dim]detected:[/] {', '.join(components)}")


def _load() -> tuple[Path, object]:
    try:
        config_path = find_config()
    except FileNotFoundError as exc:
        err.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc
    return config_path.parent, load_config(config_path)


@app.command()
def status() -> None:
    """Brief summary of pending bumps (alias of ``plan`` without reasons)."""
    repo, config = _load()
    plan_obj = build_plan(repo, config)
    if not plan_obj:
        console.print("[dim]no bumps pending[/]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("component")
    table.add_column("current")
    table.add_column("→")
    table.add_column("next")
    table.add_column("kind")
    table.add_column("reasons", overflow="fold")
    for bump in plan_obj:
        table.add_row(
            bump.component,
            str(bump.current),
            "→",
            str(bump.next),
            bump.kind,
            "\n".join(bump.reason_summaries()),
        )
    console.print(table)


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
    plan_obj = build_plan(repo, config, pre=pre, finalize=finalize)

    if output == "json":
        payload = {
            "bumps": {
                bump.component: {
                    "current": str(bump.current),
                    "next": bump.next,
                    "kind": bump.kind,
                    "reasons": [r.to_dict() for r in bump.reasons],
                }
                for bump in plan_obj
            }
        }
        console.print_json(data=payload)
        return

    if not plan_obj:
        console.print("[dim]no bumps pending[/]")
        return

    for bump in plan_obj:
        header = (
            f"[bold]{bump.component}[/]: "
            f"{bump.current} → {bump.next} "
            f"[cyan]({bump.kind})[/]"
        )
        console.print(header)
        for reason in bump.reasons:
            console.print(f"  • {reason.summary()}")
        console.print()


@app.command()
def explain(
    component: str = typer.Argument(..., help="Component to explain."),
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

    plan_obj = build_plan(repo, config)
    bump = plan_obj.bumps.get(component)
    if bump is None:
        console.print(
            f"[bold]{component}[/]: [dim]no bump pending — "
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


def _resolve_maintainer(repo: Path, configured: str | None) -> str:
    """Pick a Debian-format maintainer string ``Name <email>``.

    Priority: explicit config -> ``Maintainer:`` line in ``debian/control``
    -> ``git config user.name`` + ``git config user.email`` -> placeholder.
    """
    if configured:
        return configured
    control = repo / "debian" / "control"
    if control.is_file():
        for line in control.read_text(encoding="utf-8").splitlines():
            if line.startswith("Maintainer:"):
                return line[len("Maintainer:"):].strip()
    name_proc = subprocess.run(
        ["git", "config", "user.name"],
        cwd=repo, capture_output=True, text=True,
    )
    email_proc = subprocess.run(
        ["git", "config", "user.email"],
        cwd=repo, capture_output=True, text=True,
    )
    name = name_proc.stdout.strip()
    email = email_proc.stdout.strip()
    if name and email:
        return f"{name} <{email}>"
    return "Unknown <unknown@example.com>"


def _component_relevant_commits(
    name: str,
    config,  # Config
    repo: Path,
    matcher: ComponentMatcher,
    *,
    since_stable: bool = False,
):
    """Conventional commits owning ``name`` since the component's last tag.

    Release commits matching ``project.release_commit_pattern`` are filtered
    out so they don't pollute the changelog body. When ``since_stable`` is
    True, the range starts at the previous *stable* tag instead — used by
    the ``consolidate`` and ``promote`` finalize strategies so the final
    section enumerates everything since the last shipped release.
    """
    import re

    prefix = tag_prefix(config.tag_format_for(name), name)
    since = (
        latest_stable_tag(repo, prefix)
        if since_stable
        else latest_tag(repo, prefix)
    )
    release_re = re.compile(config.project.release_commit_pattern)
    return [
        c
        for c in commits_since(repo, since)
        if c.is_conventional
        and not release_re.match(_commit_header(c))
        and any(matcher.match(f) == name for f in c.files)
    ]


def _commit_header(commit) -> str:
    if commit.scope:
        return f"{commit.type}({commit.scope}): {commit.subject}"
    return f"{commit.type}: {commit.subject}"


def _is_finalize(planned) -> bool:
    """A finalize op is any planned bump that turns a pre-release into a
    final version (either via --finalize or auto-finalize when --pre isn't
    set on a current pre-release)."""
    return planned.current.is_prerelease and planned.pre is None


def _bump_debian(
    name: str,
    comp,  # Component
    config,  # Config
    repo: Path,
    matcher: ComponentMatcher,
    new_version: str,
    *,
    is_finalize: bool,
    dry_run: bool,
    written: list[Path],
    changelogs_updated: list[str],
) -> None:
    """Apply a debian-format bump: render and prepend a fresh stanza.

    The git tag uses the semver form (``mypkg-v1.3.0-rc.1``) so multicz can
    re-read it later via :class:`packaging.version.Version`; only the
    *changelog file* gets the Debian-style ``~rc1`` rendering.

    On finalize, the project's :attr:`finalize_strategy` controls whether
    the new stanza enumerates commits since the last RC (``annotate``) or
    since the last *stable* tag (``consolidate`` / ``promote``), and whether
    the now-superseded ``~rc*`` stanzas are removed from the file
    (``promote`` only).
    """
    settings = comp.debian
    if dry_run:
        return

    strategy = config.project.finalize_strategy
    use_stable_since = is_finalize and strategy in {"consolidate", "promote"}

    relevant = _component_relevant_commits(
        name, config, repo, matcher, since_stable=use_stable_since
    )
    debian_version = format_debian_version(
        new_version,
        debian_revision=settings.debian_revision,
        epoch=settings.epoch,
    )
    maintainer = _resolve_maintainer(repo, settings.maintainer)
    stanza = render_stanza(
        package=name,
        version=debian_version,
        distribution=settings.distribution,
        urgency=settings.urgency,
        commits=relevant,
        maintainer=maintainer,
    )

    changelog_path = repo / settings.changelog
    existing = (
        changelog_path.read_text(encoding="utf-8")
        if changelog_path.is_file()
        else ""
    )
    if is_finalize and strategy == "promote":
        existing = drop_prerelease_stanzas(existing, new_version)
    changelog_path.parent.mkdir(parents=True, exist_ok=True)
    changelog_path.write_text(prepend_stanza(existing, stanza), encoding="utf-8")
    if changelog_path not in written:
        written.append(changelog_path)
    changelogs_updated.append(str(settings.changelog))


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
    no_changelog: bool = typer.Option(
        False, "--no-changelog",
        help="Skip CHANGELOG.md updates even if components declare one.",
    ),
    pre: str = typer.Option(
        None, "--pre",
        help="Enter or continue a pre-release cycle with this label "
             "(e.g. 'rc', 'alpha', 'beta'). Increments the counter when "
             "the current version is already in the same cycle.",
    ),
    finalize: bool = typer.Option(
        False, "--finalize",
        help="Drop a pre-release suffix and ship the final version. Works "
             "even when there are no new commits since the rc tag.",
    ),
) -> None:
    """Compute and apply the bump plan to all configured files."""
    if pre is not None and finalize:
        err.print("[red]--pre and --finalize are mutually exclusive[/]")
        raise typer.Exit(code=1)

    repo, config = _load()
    plan = build_plan(repo, config, pre=pre, finalize=finalize)

    if component:
        plan.bumps = {n: b for n, b in plan.bumps.items() if n in set(component)}

    if not plan:
        if output == "json":
            console.print_json(data={"bumps": {}})
        else:
            console.print("[dim]no bumps pending[/]")
        return

    matcher = ComponentMatcher(config.components)
    applied: dict[str, dict[str, str]] = {}
    written: list[Path] = []
    changelogs_updated: list[str] = []
    for planned in plan:
        comp = config.components[planned.component]
        new_version = str(planned.next)

        is_final = _is_finalize(planned)

        if comp.format == "debian":
            _bump_debian(
                planned.component,
                comp,
                config,
                repo,
                matcher,
                new_version,
                is_finalize=is_final,
                dry_run=dry_run,
                written=written,
                changelogs_updated=changelogs_updated,
            )
        else:
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

            if comp.changelog and not no_changelog and not dry_run:
                strategy = config.project.finalize_strategy
                use_stable_since = is_final and strategy in {"consolidate", "promote"}
                relevant = _component_relevant_commits(
                    planned.component, config, repo, matcher,
                    since_stable=use_stable_since,
                )
                changelog_path = repo / comp.changelog
                update_changelog_file(
                    changelog_path,
                    new_version,
                    relevant,
                    sections=config.project.changelog_sections,
                    breaking_title=config.project.breaking_section_title,
                    other_title=config.project.other_section_title,
                    drop_prereleases=is_final and strategy == "promote",
                )
                if changelog_path not in written:
                    written.append(changelog_path)
                changelogs_updated.append(str(comp.changelog))

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
            tag_name = config.tag_format_for(name).format(
                component=name, version=info["next"]
            )
            _git(repo, "tag", "-m", f"{name} {info['next']}", tag_name)
            tags_created.append(tag_name)
        git_summary["tags"] = tags_created

    if not dry_run and push:
        _git(repo, "push", "--follow-tags")
        git_summary["pushed"] = "yes"

    if output == "json":
        console.print_json(
            data={
                "bumps": applied,
                "dry_run": dry_run,
                "git": git_summary,
                "changelogs": changelogs_updated,
            }
        )
        return

    verb = "would bump" if dry_run else "bumped"
    for name, info in applied.items():
        console.print(
            f"[green]{verb}[/] [bold]{name}[/] {info['current']} → {info['next']} "
            f"([cyan]{info['kind']}[/])"
        )
    if changelogs_updated:
        console.print(f"[green]updated changelog[/] {', '.join(changelogs_updated)}")
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

    md_chunks: list[str] = []

    for name in names:
        if name not in config.components:
            err.print(f"[red]unknown component:[/] {name}")
            raise typer.Exit(code=1)
        prefix = tag_prefix(config.tag_format_for(name), name)
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
            body = render_body(
                relevant,
                sections=config.project.changelog_sections,
                breaking_title=config.project.breaking_section_title,
                other_title=config.project.other_section_title,
            )
            md_chunks.append(f"{heading}\n\n{body}")
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
        print("\n".join(chunk.rstrip() + "\n" for chunk in md_chunks).rstrip() + "\n")


@app.command()
def check(
    file: str = typer.Argument(
        ..., help="Commit message file (use '-' to read from stdin).",
    ),
    types: list[str] = typer.Option(
        None, "--type",
        help="Restrict allowed commit types (repeatable). Defaults to the full set.",
    ),
) -> None:
    """Validate a commit message file against the conventional-commits regex.

    Designed for use as a ``commit-msg`` git hook:

    \b
    .git/hooks/commit-msg
    -----
    #!/bin/sh
    exec multicz check "$1"
    """
    if file == "-":
        message = sys.stdin.read()
    else:
        path = Path(file)
        if not path.is_file():
            err.print(f"[red]not a file:[/] {file}")
            raise typer.Exit(code=1)
        message = path.read_text(encoding="utf-8")

    allowed = tuple(types) if types else DEFAULT_TYPES
    error = validate_message(message, allowed_types=allowed)
    if error is not None:
        err.print(f"[red]invalid commit message:[/] {error}")
        first = next((line for line in message.splitlines() if line.strip()), "")
        if first:
            err.print(f"[dim]got:[/] {first}")
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
