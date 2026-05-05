# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz bump`` - compute and apply the bump plan to all configured files."""

from __future__ import annotations

import hashlib
import shlex
import subprocess
from pathlib import Path

import typer

from ...changelog import (
    drop_prerelease_stanzas,
    format_debian_version,
    prepend_stanza,
    render_stanza,
    update_changelog_file,
)
from ...components import ComponentMatcher
from ...state import (
    STATE_SCHEMA_VERSION,
    ComponentState,
    State,
    now_iso,
    write_state,
)
from ...writers import write_value
from .. import app, console, err
from .._shared import (
    _append_step_summary,
    _build_plan_or_exit,
    _cascade_entries_for,
    _component_relevant_commits,
    _load,
    _parse_force_specs,
)


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
    dirty both before and after with different content - the
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
        sections=config.project.changelog_sections,
        breaking_title=config.project.breaking_section_title,
        other_title=config.project.other_section_title,
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

    # Optional parallel markdown rendering: when `[components.<name>]
    # .changelog` is set on a debian-format component, multicz also
    # writes a keep-a-changelog Markdown file alongside the Debian
    # stanza. The Debian file stays the version source of truth; the
    # Markdown copy is purely for human readers (GitHub Releases,
    # repo browsing). Cascades don't apply here — debian-format
    # components reject mirrors entirely.
    if comp.changelog is not None:
        md_path = repo / comp.changelog
        md_path.parent.mkdir(parents=True, exist_ok=True)
        update_changelog_file(
            md_path,
            new_version,
            relevant,
            sections=config.project.changelog_sections,
            breaking_title=config.project.breaking_section_title,
            other_title=config.project.other_section_title,
            drop_prereleases=is_finalize and strategy == "promote",
        )
        if md_path not in written:
            written.append(md_path)
        changelogs_updated.append(str(comp.changelog))


def _release_commit_message(
    applied: dict[str, dict[str, str]],
    template: str,
) -> str:
    """Render the release commit message from a template with placeholders.

    Available placeholders:

    * ``{summary}``    - ``api 1.2.0 -> 1.3.0, chart 0.4.0 -> 0.5.0``
    * ``{components}`` - ``api v1.3.0, chart v0.5.0`` (versions only, ``v`` prefixed)
    * ``{body}``       - bullet list with kind annotations
    * ``{count}``      - number of components bumped

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
        tag = tag_index.get(name) or "-"
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
             "placeholders are expanded - the string is used as-is.",
    ),
    force: list[str] = typer.Option(
        None, "--force",
        help="Force-bump <name>:<kind>. Repeatable. Bypasses commit "
             "detection - use for manual rebuilds (e.g. weekly base "
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
                "[dim]no bumps pending - "
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
                # Surface mirror/trigger cascades as a Dependencies
                # section: when a release is purely cascade-driven
                # (e.g. chart bumps because api updated appVersion),
                # this is the only thing that explains *why* the
                # release exists.
                cascade_entries = _cascade_entries_for(planned, plan, config)
                changelog_path = repo / comp.changelog
                update_changelog_file(
                    changelog_path,
                    new_version,
                    relevant,
                    sections=config.project.changelog_sections,
                    breaking_title=config.project.breaking_section_title,
                    other_title=config.project.other_section_title,
                    drop_prereleases=is_final and strategy == "promote",
                    cascades=cascade_entries,
                    cascade_title=config.project.cascade_section_title,
                    cascade_format=config.project.cascade_changelog_format,
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
    # Detection compares content hashes - not just the dirty-paths set -
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
