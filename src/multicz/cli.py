"""Command line interface for multicz."""

from __future__ import annotations

import hashlib
import shlex
import subprocess
import sys
from pathlib import Path

import typer
from packaging.version import Version
from rich.console import Console
from rich.table import Table

from . import __version__
from .changelog import render_body, update_changelog_file
from .commits import (
    DEFAULT_TYPES,
    commits_in_range,
    commits_since,
    latest_stable_tag,
    latest_tag,
    previous_stable_tag,
    previous_tag,
    tag_prefix,
    validate_message,
)
from .components import ComponentMatcher
from .config import CONFIG_FILENAME, Component, find_config, load_config
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
    NonConventionalCommitsError,
    TriggerReason,
    build_plan,
)
from .state import (
    STATE_SCHEMA_VERSION,
    ComponentState,
    State,
    load_state,
    now_iso,
    write_state,
)
from .validation import validate as run_validation
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
) -> None:
    """Generate a multicz.toml tailored to the working tree.

    By default the working tree is scanned for ``pyproject.toml``,
    ``charts/*/Chart.yaml``, ``package.json``, ``Cargo.toml``, ``go.mod``,
    ``gradle.properties`` and ``debian/changelog``; one component is
    emitted per detected manifest. ``--bare`` writes a generic
    single-component stub instead — useful when bootstrapping a brand
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

    # Compute components (or skip when --bare)
    components: dict[str, Component] | None = None
    if not bare:
        components = discover_components(target_dir)
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


def _load() -> tuple[Path, object]:
    from pydantic import ValidationError
    try:
        config_path = find_config()
    except FileNotFoundError as exc:
        err.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc
    try:
        return config_path.parent, load_config(config_path)
    except ValidationError as exc:
        err.print(f"[red]invalid {config_path}:[/]")
        for error in exc.errors():
            loc = " -> ".join(str(p) for p in error["loc"])
            err.print(f"  [yellow]{loc}[/]: {error['msg']}")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        err.print(f"[red]invalid {config_path}:[/] {exc}")
        raise typer.Exit(code=1) from exc


def _parse_force_specs(specs: list[str], config) -> dict[str, str]:
    """Parse ``--force <name>:<kind>`` flags into a dict.

    Validates the component name and kind upfront so the user gets a
    clear error before the planner runs.
    """
    valid_kinds = {"major", "minor", "patch"}
    parsed: dict[str, str] = {}
    for spec in specs or []:
        if ":" not in spec:
            err.print(
                f"[red]invalid --force spec[/] {spec!r}: "
                "expected NAME:KIND (e.g. api:patch)"
            )
            raise typer.Exit(code=1)
        name, _, kind = spec.partition(":")
        if name not in config.components:
            err.print(f"[red]unknown component:[/] {name}")
            raise typer.Exit(code=1)
        if kind not in valid_kinds:
            err.print(
                f"[red]invalid kind[/] {kind!r}: "
                "must be major, minor, or patch"
            )
            raise typer.Exit(code=1)
        parsed[name] = kind
    return parsed


def _append_step_summary(path: Path, lines: list[str]) -> None:
    """Append a markdown block to ``path``.

    Mirrors GitHub Actions' ``$GITHUB_STEP_SUMMARY`` semantics: each
    step's content is appended; the runner concatenates everything into
    the workflow's run-page summary. Safe to call from local shells —
    the file is just a text file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
        fh.write("\n")


def _append_plan_summary(path: Path, plan_obj, *, header: str) -> None:
    """Render a plan as a markdown summary and append it."""
    lines = [f"## {header}", ""]
    if not plan_obj:
        lines.append("_No bumps pending._")
        _append_step_summary(path, lines)
        return

    lines.extend([
        "| component | current | next | kind |",
        "|---|---|---|---|",
    ])
    for bump in plan_obj:
        lines.append(
            f"| `{bump.component}` | `{bump.current}` | "
            f"`{bump.next}` | {bump.kind} |"
        )
    lines.append("")
    for bump in plan_obj:
        lines.append(
            f"### `{bump.component}` — {bump.current} → {bump.next} "
            f"({bump.kind})"
        )
        lines.append("")
        for reason in bump.reasons:
            lines.append(f"- {reason.summary()}")
        lines.append("")
    _append_step_summary(path, lines)


def _append_bump_summary(
    path: Path,
    applied: dict,
    config,
    git_summary: dict,
    *,
    dry_run: bool,
) -> None:
    """Render the applied bump (post-write) as a markdown summary."""
    header = "Released" if not dry_run else "Would release"
    lines = [f"## {header}", ""]
    if not applied:
        lines.append("_No bumps pending._")
        _append_step_summary(path, lines)
        return

    lines.extend([
        "| component | current | next | kind | tag |",
        "|---|---|---|---|---|",
    ])
    tags = git_summary.get("tags") or []
    tag_index = {t.split("-v", 1)[0] if "-v" in t else None: t for t in tags}
    # Fall back to format string lookup when tag_format isn't `<comp>-v<ver>`.
    for name, info in applied.items():
        tag = tag_index.get(name) or "—"
        for t in tags:
            if config.tag_format_for(name).format(
                component=name, version=info["next"]
            ) == t:
                tag = t
                break
        lines.append(
            f"| `{name}` | `{info['current']}` | `{info['next']}` | "
            f"{info['kind']} | `{tag}` |"
        )
    lines.append("")
    if git_summary.get("commit"):
        lines.append(f"**Release commit:** `{git_summary['commit'][:12]}`")
    if tags:
        lines.append(f"**Tags created:** {', '.join(f'`{t}`' for t in tags)}")
    if git_summary.get("pushed"):
        lines.append("**Pushed:** yes")
    if git_summary.get("signed_commit"):
        lines.append("**Signed commit:** yes")
    if git_summary.get("signed_tags"):
        lines.append("**Signed tags:** yes")
    _append_step_summary(path, lines)


def _build_plan_or_exit(repo, config, **kwargs):
    """Wrap build_plan() and surface NonConventionalCommitsError as a clean
    typer.Exit instead of a raw traceback."""
    try:
        return build_plan(repo, config, **kwargs)
    except NonConventionalCommitsError as exc:
        err.print(
            f"[red]✗ {len(exc.offenders)} non-conventional commit(s) "
            "blocking the plan[/] [dim](unknown_commit_policy='error')[/]"
        )
        for sha, subject in exc.offenders:
            err.print(f"  - {sha[:7]}: {subject}")
        err.print(
            "\n[dim]Either rewrite their headers as conventional commits "
            "(`git rebase -i`), or set "
            "[bold]unknown_commit_policy = \"ignore\"[/] (or "
            "[bold]\"patch\"[/]) in [project].[/]"
        )
        raise typer.Exit(code=1) from exc


@app.command()
def status(
    since: str = typer.Option(
        None, "--since",
        help="Override the commit window: use this ref instead of each "
             "component's last tag. Useful for PR previews "
             "(--since origin/main).",
    ),
) -> None:
    """Brief summary of pending bumps (alias of ``plan`` without reasons)."""
    repo, config = _load()
    plan_obj = _build_plan_or_exit(repo, config, since=since)
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
    since: str = typer.Option(
        None, "--since",
        help="Override the commit window: use this ref instead of each "
             "component's last tag. Useful for PR previews "
             "(--since origin/main) or migration scenarios "
             "(--since HEAD~10).",
    ),
    force: list[str] = typer.Option(
        None, "--force",
        help="Force-bump <name>:<kind>. Repeatable. Bypasses commit "
             "detection — use for manual rebuilds (CVE base image refresh, "
             "weekly artefact rebuild, …).",
    ),
    summary: Path = typer.Option(
        None, "--summary",
        help="Append a markdown summary of the plan to this file. "
             "Wire to $GITHUB_STEP_SUMMARY in CI to get a release "
             "preview at the top of the workflow run page.",
        dir_okay=False,
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
    forced = _parse_force_specs(force, config) if force else {}
    plan_obj = _build_plan_or_exit(
        repo, config, pre=pre, finalize=finalize, since=since, force=forced or None
    )

    if summary is not None:
        _append_plan_summary(summary, plan_obj, header="Release plan")

    if output == "json":
        payload = {
            "schema_version": 1,
            "bumps": {
                bump.component: {
                    "current_version": str(bump.current),
                    "next_version": bump.next,
                    "kind": bump.kind,
                    "reasons": [r.to_dict() for r in bump.reasons],
                    "artifacts": [
                        a.render(component=bump.component, version=bump.next)
                        for a in config.components[bump.component].artifacts
                    ],
                }
                for bump in plan_obj
            },
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
def state(
    output: str = typer.Option("text", "--output", "-o", help="text | json"),
) -> None:
    """Inspect the optional state file written after each successful bump.

    The state file is opt-in via ``[project].state_file = "..."``. It
    records the per-component version, the expected tag name (when
    ``--tag`` was used at bump time), the SHA the bump was computed
    against, and a UTC timestamp.
    """
    repo, config = _load()
    if config.project.state_file is None:
        err.print(
            "[red]no state_file configured[/] — set "
            "[bold][project].state_file[/] in multicz.toml"
        )
        raise typer.Exit(code=1)

    path = repo / config.project.state_file
    state_obj = load_state(path)
    if state_obj is None:
        if output == "json":
            console.print_json(data=None)
        else:
            console.print(
                f"[dim]{config.project.state_file} not yet written[/]"
            )
        return

    if output == "json":
        console.print_json(data=state_obj.to_dict())
        return

    console.print(
        f"[bold]state[/] {config.project.state_file} "
        f"(schema v{state_obj.version})"
    )
    console.print(f"  git_head:  {state_obj.git_head_short or state_obj.git_head}")
    console.print(f"  timestamp: {state_obj.timestamp}")
    for name, comp in state_obj.components.items():
        line = f"  [bold]{name}[/]: {comp.version}"
        if comp.tag:
            line += f"  [dim]({comp.tag})[/]"
        console.print(line)


@app.command()
def changed(
    since: str = typer.Option(
        None, "--since",
        help="Reference to compare against (e.g. origin/main, HEAD~5). "
             "When omitted, each component is compared against its own "
             "last tag — same window as the planner uses for bumps.",
    ),
    output: str = typer.Option(
        "text", "--output", "-o", help="text | json",
    ),
) -> None:
    """List components whose files changed since the given reference.

    Designed for CI matrix gating: only run tests/builds for components
    that actually changed.

    \b
    GitHub Actions example:
      jobs:
        detect:
          outputs:
            changed: ${{ steps.c.outputs.list }}
          steps:
            - id: c
              run: echo "list=$(multicz changed --since origin/main \\
                                 --output json | jq -c .changed)" >> $GITHUB_OUTPUT
        test:
          needs: detect
          strategy:
            matrix:
              component: ${{ fromJson(needs.detect.outputs.changed) }}

    Without --since, the answer is per-component (same window as the
    planner). With --since, every component shares the reference —
    ideal for "what changed in this PR vs main".

    Release commits matching ``project.release_commit_pattern`` are
    filtered out so a previous ``multicz bump --commit`` doesn't keep
    flagging components as changed forever.
    """
    import re

    repo, config = _load()
    matcher = ComponentMatcher(config.components)
    release_re = re.compile(config.project.release_commit_pattern)

    changed_list: list[str] = []
    unchanged_list: list[str] = []
    for name in config.components:
        if since is None:
            prefix = tag_prefix(config.tag_format_for(name), name)
            ref: str | None = latest_tag(repo, prefix)
        else:
            ref = since
        commits = commits_since(repo, ref)
        owns_change = False
        for c in commits:
            if release_re.match(_commit_header(c)):
                continue
            for f in c.files:
                if matcher.match(f) == name:
                    owns_change = True
                    break
            if owns_change:
                break
        if owns_change:
            changed_list.append(name)
        else:
            unchanged_list.append(name)

    if output == "json":
        console.print_json(
            data={"changed": changed_list, "unchanged": unchanged_list}
        )
        return

    for name in changed_list:
        print(name)


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
            from .planner import _current_version
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


@app.command(name="release-notes")
def release_notes_cmd(
    component: str = typer.Argument(
        None,
        help="Component to render notes for. Required unless --all or --tag is set.",
    ),
    all_: bool = typer.Option(
        False, "--all",
        help="Render notes for every component with a planned bump.",
    ),
    tag: str = typer.Option(
        None, "--tag",
        help="Render notes for a past release tag (e.g. api-v1.3.0).",
    ),
    output: str = typer.Option(
        "md", "--output", "-o", help="md | text | json",
    ),
) -> None:
    """Generate release notes for an upcoming bump or a past tag.

    Designed for piping into ``gh release create`` or pasting into a
    GitHub/GitLab Release UI: no file is written, the output IS the
    notes.

    \b
    Default (notes for the upcoming bump — same set as `plan`):
      multicz release-notes api
      multicz release-notes --all

    Retrospective (what shipped in a tagged release):
      multicz release-notes --tag api-v1.3.0

    Stable release tags look at commits since the previous *stable*
    tag (so v1.3.0 lists everything since v1.2.0, not just since
    v1.3.0-rc.2). Pre-release tags use the immediately previous tag
    so each rc shows only the delta.
    """
    if tag is None and not all_ and component is None:
        err.print(
            "[red]specify a component, --all, or --tag <tag>[/]"
        )
        raise typer.Exit(code=1)
    if tag is not None and (all_ or component is not None):
        err.print(
            "[red]--tag is exclusive with a component name and --all[/]"
        )
        raise typer.Exit(code=1)

    repo, config = _load()
    matcher = ComponentMatcher(config.components)

    sections: list[dict] = []

    if tag is not None:
        owner = _component_for_tag(config, tag)
        if owner is None:
            err.print(
                f"[red]tag {tag!r} doesn't match any component's tag_format[/]"
            )
            raise typer.Exit(code=1)
        prefix = tag_prefix(config.tag_format_for(owner), owner)
        target_version = Version(tag[len(prefix):])
        if target_version.is_prerelease:
            prev = previous_tag(repo, prefix, tag)
        else:
            prev = previous_stable_tag(repo, prefix, tag)
        commits = _filtered_commits_in_range(
            owner, config, repo, matcher, since=prev, end=tag
        )
        sections.append({
            "component": owner,
            "from": prev,
            "from_version": prev[len(prefix):] if prev else None,
            "to_version": str(target_version),
            "commits": commits,
        })
    else:
        plan_obj = _build_plan_or_exit(repo, config)
        if all_:
            targets = list(plan_obj.bumps)
        else:
            if component not in config.components:
                err.print(f"[red]unknown component:[/] {component}")
                raise typer.Exit(code=1)
            targets = [component]

        for name in targets:
            bump = plan_obj.bumps.get(name)
            if bump is None:
                if not all_:
                    console.print(
                        f"[dim]no pending bump for {name}[/]"
                    )
                    return
                continue
            commits = _component_relevant_commits(name, config, repo, matcher)
            sections.append({
                "component": name,
                "from": None,
                "from_version": str(bump.current),
                "to_version": bump.next,
                "commits": commits,
            })

    if not sections:
        if output == "json":
            console.print_json(data={"sections": []})
        else:
            console.print("[dim]nothing to release[/]")
        return

    if output == "json":
        console.print_json(data={
            "sections": [
                {
                    "component": s["component"],
                    "from_version": s["from_version"],
                    "to_version": s["to_version"],
                    "commits": [
                        {
                            "sha": c.sha,
                            "type": c.type,
                            "scope": c.scope,
                            "breaking": c.breaking,
                            "subject": c.subject,
                        }
                        for c in s["commits"]
                    ],
                }
                for s in sections
            ]
        })
        return

    if output == "text":
        for s in sections:
            range_label = (
                f"{s['from_version']} → {s['to_version']}"
                if s["from_version"]
                else s["to_version"]
            )
            console.print(f"[bold]{s['component']}[/] {range_label}")
            for c in s["commits"]:
                bang = "!" if c.breaking else ""
                scope = f"({c.scope})" if c.scope else ""
                console.print(
                    f"  - {c.type}{scope}{bang}: {c.subject}  "
                    f"[dim]({c.sha[:7]})[/]"
                )
            console.print()
        return

    # md (default)
    chunks: list[str] = []
    multi = len(sections) > 1 or all_
    for s in sections:
        body = render_body(
            s["commits"],
            sections=config.project.changelog_sections,
            breaking_title=config.project.breaking_section_title,
            other_title=config.project.other_section_title,
        )
        if multi:
            range_label = (
                f"{s['from_version']} → {s['to_version']}"
                if s["from_version"]
                else s["to_version"]
            )
            chunks.append(f"## {s['component']} {range_label}\n\n{body}".rstrip() + "\n")
        else:
            chunks.append(body.rstrip() + "\n")
    print("\n".join(chunks).rstrip() + "\n")


def _component_for_tag(config, tag: str) -> str | None:
    """Find the component whose tag_format produces a prefix that ``tag`` starts with."""
    best_match: tuple[int, str] | None = None
    for name in config.components:
        prefix = tag_prefix(config.tag_format_for(name), name)
        if tag.startswith(prefix):
            # Prefer the longest match (more specific prefix wins)
            score = len(prefix)
            if best_match is None or score > best_match[0]:
                best_match = (score, name)
    return best_match[1] if best_match else None


def _filtered_commits_in_range(
    name: str, config, repo: Path, matcher, *, since: str | None, end: str
):
    """Same filtering as _component_relevant_commits but for a custom range."""
    import re

    release_re = re.compile(config.project.release_commit_pattern)
    ignored = config.ignored_types_for(name)
    return [
        c
        for c in commits_in_range(repo, since, end)
        if c.is_conventional
        and not release_re.match(_commit_header(c))
        and c.type.lower() not in ignored
        and any(matcher.match(f) == name for f in c.files)
    ]


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


def _porcelain_paths(repo: Path) -> set[str]:
    """Repo-relative paths currently dirty in the working tree.

    Used to identify candidate paths to hash before/after running
    ``post_bump`` hooks. A pure set diff would miss a file that's
    dirty both before and after with different content — the
    canonical case being ``uv run`` itself silently re-syncing
    ``uv.lock`` before multicz even gets to run.
    """
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo, capture_output=True, text=True,
    )
    if out.returncode != 0:
        return set()
    paths: set[str] = set()
    for line in out.stdout.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:]
        # Renames render as "OLD -> NEW"; we care about the new path only.
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        paths.add(rest)
    return paths


def _hash_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _run_post_bump_hook(repo: Path, command: str) -> None:
    """Execute a single ``post_bump`` shell command in ``repo``."""
    args = shlex.split(command)
    if not args:
        return
    # stderr, so `multicz bump --output json | jq` stays parseable.
    err.print(f"  [dim]post_bump:[/] {command}")
    result = subprocess.run(
        args, cwd=repo, capture_output=True, text=True
    )
    if result.returncode != 0:
        err.print(
            f"[red]post_bump hook failed[/] (exit {result.returncode}): "
            f"{command}"
        )
        if result.stderr.strip():
            err.print(result.stderr.strip())
        raise typer.Exit(code=1)


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

    Filters applied:

    * release commits matching ``project.release_commit_pattern`` are
      skipped so the chore(release) lines don't pollute the changelog.
    * commits whose type is in the component's effective ``ignored_types``
      (project + component, union) are skipped entirely.

    When ``since_stable`` is True, the range starts at the previous
    *stable* tag instead — used by the ``consolidate`` and ``promote``
    finalize strategies.
    """
    import re

    prefix = tag_prefix(config.tag_format_for(name), name)
    since = (
        latest_stable_tag(repo, prefix)
        if since_stable
        else latest_tag(repo, prefix)
    )
    release_re = re.compile(config.project.release_commit_pattern)
    ignored = config.ignored_types_for(name)
    return [
        c
        for c in commits_since(repo, since)
        if c.is_conventional
        and not release_re.match(_commit_header(c))
        and c.type.lower() not in ignored
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


def _release_commit_message(
    applied: dict[str, dict[str, str]],
    template: str,
) -> str:
    """Render the release commit message from a template with placeholders.

    Available placeholders:

    * ``{summary}``    — ``api 1.2.0 -> 1.3.0, chart 0.4.0 -> 0.5.0``
    * ``{components}`` — ``api v1.3.0, chart v0.5.0`` (versions only, ``v`` prefixed)
    * ``{body}``       — bullet list with kind annotations
    * ``{count}``      — number of components bumped

    Literal ``{`` and ``}`` in a template should be escaped as ``{{`` / ``}}``.
    """
    summary = ", ".join(
        f"{name} {info['current']} -> {info['next']}"
        for name, info in applied.items()
    )
    components = ", ".join(
        f"{name} v{info['next']}" for name, info in applied.items()
    )
    body = "\n".join(
        f"- {name}: {info['current']} -> {info['next']} ({info['kind']})"
        for name, info in applied.items()
    )
    rendered = template.format(
        summary=summary,
        components=components,
        body=body,
        count=len(applied),
    )
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


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
    commit_message: str = typer.Option(
        None, "--commit-message", "-m",
        help="Verbatim release commit message (overrides the project's "
             "release_commit_message template). Like 'git commit -m', no "
             "placeholders are expanded — the string is used as-is.",
    ),
    force: list[str] = typer.Option(
        None, "--force",
        help="Force-bump <name>:<kind>. Repeatable. Bypasses commit "
             "detection — use for manual rebuilds (e.g. weekly base "
             "image refresh: `--force api:patch`).",
    ),
    sign: bool = typer.Option(
        False, "--sign",
        help="GPG-sign the release commit AND tags. Equivalent to setting "
             "[project].sign_commits=true and [project].sign_tags=true. "
             "Either source enables signing; the CLI flag never disables.",
    ),
    summary: Path = typer.Option(
        None, "--summary",
        help="Append a markdown summary of what was released to this file. "
             "Wire to $GITHUB_STEP_SUMMARY in CI to surface the release on "
             "the workflow run page.",
        dir_okay=False,
    ),
) -> None:
    """Compute and apply the bump plan to all configured files."""
    if pre is not None and finalize:
        err.print("[red]--pre and --finalize are mutually exclusive[/]")
        raise typer.Exit(code=1)
    if commit_message is not None and not commit:
        err.print("[red]--commit-message requires --commit[/]")
        raise typer.Exit(code=1)

    repo, config = _load()
    forced = _parse_force_specs(force, config) if force else {}
    plan = _build_plan_or_exit(
        repo, config, pre=pre, finalize=finalize, force=forced or None
    )

    if component:
        plan.bumps = {n: b for n, b in plan.bumps.items() if n in set(component)}

    if not plan:
        if output == "json":
            console.print_json(data={"bumps": {}})
        else:
            console.print(
                "[dim]no bumps pending — "
                "use [bold]--force <name>:<kind>[/] for a manual bump[/]"
            )
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
    # Optional state file: written before the commit so it lands in the
    # release commit alongside the version-file changes.
    if not dry_run and config.project.state_file is not None:
        state_path = repo / config.project.state_file
        try:
            head_before = _git(repo, "rev-parse", "HEAD").strip()
        except Exception:
            head_before = ""
        components_state: dict[str, ComponentState] = {}
        for name, info in applied.items():
            tag_name: str | None = None
            if tag:
                tag_name = config.tag_format_for(name).format(
                    component=name, version=info["next"]
                )
            components_state[name] = ComponentState(
                version=info["next"],
                tag=tag_name,
                tag_sha=None,
            )
        state_obj = State(
            version=STATE_SCHEMA_VERSION,
            git_head=head_before,
            git_head_short=head_before[:7] if head_before else "",
            timestamp=now_iso(),
            components=components_state,
        )
        write_state(state_path, state_obj)
        if state_path not in written:
            written.append(state_path)

    sign_commits_flag = sign or config.project.sign_commits
    sign_tags_flag = sign or config.project.sign_tags

    # post_bump hooks: run after every file write (bump_files, mirrors,
    # changelog, state) so commands like `uv lock`, `npm install
    # --package-lock-only`, `cargo update --workspace`, `helm dependency
    # update` see the new pyproject.toml / package.json / Chart.yaml /
    # Cargo.toml. Files modified by hooks are auto-detected and folded
    # into ``written`` so they ride the release commit.
    #
    # Detection compares content hashes — not just the dirty-paths set —
    # because the entry point is typically ``uv run multicz bump``, and
    # ``uv run`` re-syncs the venv (which can rewrite ``uv.lock``) before
    # multicz code runs at all. By the time we snapshot, uv.lock is
    # already in the dirty set; a set diff would miss the *second*
    # rewrite the post_bump hook performs against the new pyproject. The
    # hash comparison catches it.
    if not dry_run and applied:
        hook_components = [
            n for n in applied if config.components[n].post_bump
        ]
        if hook_components:
            before_dirty = _porcelain_paths(repo)
            before_hashes: dict[str, str | None] = {
                relpath: _hash_file(repo / relpath)
                for relpath in before_dirty
            }
            for name in hook_components:
                for command in config.components[name].post_bump:
                    _run_post_bump_hook(repo, command)
            after_dirty = _porcelain_paths(repo)
            hook_modified: set[str] = {
                relpath
                for relpath in after_dirty
                if relpath not in before_dirty
                or _hash_file(repo / relpath) != before_hashes.get(relpath)
            }
            for relpath in sorted(hook_modified):
                path = (repo / relpath).resolve()
                if path.is_file() and path not in written:
                    written.append(path)

    if not dry_run and commit and written:
        rel_paths = [str(p.relative_to(repo)) for p in written]
        _git(repo, "add", "--", *rel_paths)
        if commit_message is not None:
            msg = commit_message  # CLI override is verbatim, no placeholders
        else:
            msg = _release_commit_message(
                applied, config.project.release_commit_message
            )
        commit_args = ["commit", "-m", msg]
        if sign_commits_flag:
            commit_args.insert(1, "-S")  # before -m so git accepts it
        _git(repo, *commit_args)
        sha = _git(repo, "rev-parse", "HEAD").strip()
        git_summary["commit"] = sha

    tags_created: list[str] = []
    if not dry_run and tag:
        for name, info in applied.items():
            tag_name = config.tag_format_for(name).format(
                component=name, version=info["next"]
            )
            tag_args = ["tag"]
            if sign_tags_flag:
                # -s creates a signed annotated tag; -m supplies the message.
                tag_args.append("-s")
            tag_args.extend(["-m", f"{name} {info['next']}", tag_name])
            _git(repo, *tag_args)
            tags_created.append(tag_name)
        git_summary["tags"] = tags_created
        if sign_tags_flag:
            git_summary["signed_tags"] = "yes"
        if sign_commits_flag and "commit" in git_summary:
            git_summary["signed_commit"] = "yes"

    if not dry_run and push:
        _git(repo, "push", "--follow-tags")
        git_summary["pushed"] = "yes"

    # Write the markdown summary for both --output json and --output text
    # so a CI step can simultaneously capture JSON for jq AND populate
    # $GITHUB_STEP_SUMMARY in the same invocation.
    if summary is not None:
        _append_bump_summary(
            summary, applied, config, git_summary, dry_run=dry_run
        )

    if output == "json":
        bumps_payload = {
            name: {
                "current_version": info["current"],
                "next_version": info["next"],
                "kind": info["kind"],
                "artifacts": [
                    a.render(component=name, version=info["next"])
                    for a in config.components[name].artifacts
                ],
            }
            for name, info in applied.items()
        }
        console.print_json(
            data={
                "schema_version": 1,
                "bumps": bumps_payload,
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
    plan = _build_plan_or_exit(repo, config)

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


@app.command(name="validate")
def validate_cmd(
    strict: bool = typer.Option(
        False, "--strict",
        help="Exit non-zero on warnings too (CI gate).",
    ),
    output: str = typer.Option(
        "text", "--output", "-o", help="text | json",
    ),
) -> None:
    """Run every config + repo sanity check and report the findings.

    Checks performed:

    \b
    - bump_files exist on disk
    - components don't claim overlapping paths (first-match-wins is
      explicit, not silent)
    - mirror targets are owned by another component (otherwise no
      cascade fires) and don't loop back to the same component
    - declared triggers form no cycle
    - mirror cascades form no cycle
    - declared changelog paths are reachable
    - the planner can resolve the current version of every component
    - debian/changelog files (when format='debian') parse correctly

    Exit code:

    \b
    0  no errors (warnings/info don't fail unless --strict)
    1  at least one error
    2  --strict and at least one warning
    """
    repo, config = _load()
    findings = run_validation(repo, config)
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    infos = [f for f in findings if f.level == "info"]

    if output == "json":
        console.print_json(data={
            "findings": [f.to_dict() for f in findings],
            "summary": {
                "errors": len(errors),
                "warnings": len(warnings),
                "info": len(infos),
            },
        })
    else:
        if not findings:
            console.print("[green]✓ no issues found[/]")
        else:
            colors = {"error": "red", "warning": "yellow", "info": "blue"}
            tags = {"error": "✗", "warning": "!", "info": "i"}
            for finding in findings:
                color = colors[finding.level]
                tag = tags[finding.level]
                comp = (
                    f"[bold]{finding.component}[/]: "
                    if finding.component
                    else ""
                )
                console.print(
                    f"[{color}]{tag}[/] {comp}{finding.message}  "
                    f"[dim]({finding.check})[/]"
                )
            console.print()
            counts: list[str] = []
            if errors:
                counts.append(
                    f"[red]{len(errors)} error{'s' if len(errors) != 1 else ''}[/]"
                )
            if warnings:
                counts.append(
                    f"[yellow]{len(warnings)} "
                    f"warning{'s' if len(warnings) != 1 else ''}[/]"
                )
            if infos:
                counts.append(f"[blue]{len(infos)} info[/]")
            console.print(", ".join(counts))

    if errors:
        raise typer.Exit(code=1)
    if strict and warnings:
        raise typer.Exit(code=2)


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
