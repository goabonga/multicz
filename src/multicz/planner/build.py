# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Compute the bump plan for every component declared in the config.

The planner is split into three passes:

1. **Direct**: each component looks at the commits made since its own last
   tag, keeps those whose changed files map back to it, and aggregates the
   strongest bump kind implied by the conventional commit headers.
2. **Triggers**: a component declared in another's ``triggers`` list inherits
   that upstream's bump kind (clamped to at least patch).
3. **Mirror cascade**: if component A writes its version into a file owned by
   component B (a ``mirror``), B receives a patch bump - keeping Helm chart
   immutability (option A from the design discussion).

All three passes share a single :func:`_promote` helper so a component can be
upgraded (e.g. patch → minor) but never downgraded.
"""

from __future__ import annotations

from pathlib import Path

from packaging.version import InvalidVersion, Version

from ..commits import (
    BumpKind,
    bump_kind_for,
    commits_since,
    latest_tag,
    latest_version,
    tag_prefix,
)
from ..config import ComponentMatcher, Config
from ..formats import FormatError, read_value
from .plan import Plan, PlannedBump, _stronger
from .reasons import (
    CommitReason,
    ManualReason,
    MirrorReason,
    NonConventionalCommitsError,
    NonConventionalReason,
    Reason,
    TriggerReason,
)


def _promote(
    plan: Plan,
    component: str,
    kind: BumpKind,
    current: Version,
    reason: Reason,
) -> bool:
    """Add or upgrade ``component`` in ``plan``. Returns True if it changed."""
    existing = plan.bumps.get(component)
    if existing is None:
        plan.bumps[component] = PlannedBump(
            component=component, current=current, kind=kind, reasons=[reason]
        )
        return True
    new_kind = _stronger(existing.kind, kind)
    changed = False
    if new_kind != existing.kind:
        existing.kind = new_kind  # type: ignore[assignment]
        changed = True
    if reason not in existing.reasons:
        existing.reasons.append(reason)
        changed = True
    return changed


def _current_version(repo: Path, config: Config, name: str) -> Version:
    """Resolve the component's current version.

    Priority:
      1. the highest matching git tag (authoritative release state),
      2. the value stored in the primary bump_file (in-tree state),
      3. a writer that claims the version-source role (e.g. the top
         stanza of a ``debian-changelog`` writer when ``bump_files``
         is empty),
      4. ``initial_version`` from the project settings (bootstrap).
    """
    prefix = tag_prefix(config.tag_format_for(name), name)
    tagged = latest_version(repo, prefix)
    if tagged is not None:
        return tagged

    comp = config.components[name]
    if comp.bump_files:
        primary = comp.bump_files[0]
        try:
            return Version(read_value(repo / primary.file, primary.key))
        except (FormatError, InvalidVersion, FileNotFoundError):
            pass
    elif comp.writers:
        from ..writers import read_version_from_writers

        claimed = read_version_from_writers(comp.writers, repo)
        if claimed is not None:
            try:
                return Version(claimed)
            except InvalidVersion:
                pass
    return Version(config.project.initial_version)


def _direct_pass(
    repo: Path,
    config: Config,
    matcher: ComponentMatcher,
    plan: Plan,
    versions: dict[str, Version],
    *,
    since_override: str | None = None,
) -> None:
    import re

    release_re = re.compile(config.project.release_commit_pattern)
    overlap_all = config.project.overlap_policy == "all"
    unknown_policy = config.project.unknown_commit_policy
    offenders: list[tuple[str, str]] = []  # for unknown_commit_policy = error

    for name in config.components:
        if since_override is None:
            prefix = tag_prefix(config.tag_format_for(name), name)
            since = latest_tag(repo, prefix)
        else:
            since = since_override
        rules = config.bump_rules_for(name)
        for commit in commits_since(repo, since):
            # Handle non-conventional commits before anything else.
            if not commit.is_conventional:
                if unknown_policy == "ignore":
                    continue
                # Both 'patch' and 'error' need to know which files in this
                # commit map to this component.
                if overlap_all:
                    owned = tuple(
                        p for p in commit.files if name in matcher.match_all(p)
                    )
                else:
                    owned = tuple(
                        p for p in commit.files if matcher.match(p) == name
                    )
                if not owned:
                    continue
                if unknown_policy == "error":
                    pair = (commit.sha, commit.subject or "")
                    if pair not in offenders:
                        offenders.append(pair)
                    continue
                # 'patch'
                reason = NonConventionalReason(
                    sha=commit.sha,
                    subject=commit.subject or "",
                    files=owned,
                )
                _promote(plan, name, "patch", versions[name], reason)
                continue

            header = (
                f"{commit.type}({commit.scope}): {commit.subject}"
                if commit.scope
                else f"{commit.type}: {commit.subject}"
            )
            if release_re.match(header):
                continue
            commit_kind = bump_kind_for(commit, rules)
            if commit_kind is None:
                continue
            if overlap_all:
                owned = tuple(
                    p for p in commit.files if name in matcher.match_all(p)
                )
            else:
                owned = tuple(
                    p for p in commit.files if matcher.match(p) == name
                )
            if not owned:
                continue

            comp = config.components[name]
            kind = commit_kind
            demoted = False
            if (
                comp.bump_policy == "scoped"
                and commit.scope is not None
                and commit.scope != name
                and kind in {"minor", "major"}
            ):
                # The commit's scope identifies a different component;
                # under scoped policy this component may only patch.
                kind = "patch"
                demoted = True

            reason = CommitReason(
                sha=commit.sha,
                type=commit.type,
                scope=commit.scope,
                breaking=commit.breaking,
                subject=commit.subject,
                files=owned,
                bump_kind=kind,
                original_kind=commit_kind if demoted else None,
            )
            _promote(plan, name, kind, versions[name], reason)

    if offenders:
        raise NonConventionalCommitsError(offenders)


def _triggers_pass(
    config: Config, plan: Plan, versions: dict[str, Version]
) -> None:
    """Cascade bumps along ``depends_on`` edges.

    The cascade kind is governed by ``project.trigger_policy``:

    * ``patch`` (default): the dependent always patches when its upstream
      bumps, regardless of the upstream's level. A dependent (e.g. a Helm
      chart) usually doesn't *gain* the upstream's feature; it just needs
      a fresh build referencing the new version.
    * ``match-upstream``: the dependent inherits the upstream's bump kind.
      ``api`` going minor → ``chart`` also goes minor. Use when the
      dependent's release semantics genuinely track the upstream's.
    """
    policy = config.project.trigger_policy
    changed = True
    while changed:
        changed = False
        for name, comp in config.components.items():
            for upstream in comp.depends_on:
                upstream_bump = plan.bumps.get(upstream)
                if upstream_bump is None:
                    continue
                cascade_kind: BumpKind = (
                    "patch" if policy == "patch" else upstream_bump.kind
                )
                reason = TriggerReason(
                    upstream=upstream,
                    upstream_kind=upstream_bump.kind,
                )
                if _promote(
                    plan,
                    name,
                    cascade_kind,
                    versions[name],
                    reason,
                ):
                    changed = True


def _mirror_pass(
    config: Config,
    matcher: ComponentMatcher,
    plan: Plan,
    versions: dict[str, Version],
) -> None:
    changed = True
    while changed:
        changed = False
        for name in list(plan.bumps):
            comp = config.components[name]
            for mirror in comp.mirrors:
                target = matcher.match(str(mirror.file))
                if target is None or target == name:
                    continue
                reason = MirrorReason(
                    upstream=name,
                    file=str(mirror.file),
                    key=mirror.key,
                )
                if _promote(
                    plan,
                    target,
                    "patch",
                    versions[target],
                    reason,
                ):
                    changed = True


def build_plan(
    repo: Path,
    config: Config,
    *,
    pre: str | None = None,
    finalize: bool = False,
    since: str | None = None,
    force: dict[str, BumpKind] | None = None,
) -> Plan:
    """Compute the bump plan for ``repo`` against ``config``.

    ``pre="rc"`` enters a release-candidate cycle. ``finalize=True`` drops
    a pre-release suffix. Both flags apply to every bumping component.

    ``since`` overrides the per-component "last tag" reference used to
    pick which commits are in scope. When set, every component reads
    commits from ``since`` to ``HEAD`` instead of from its own latest
    tag - useful for PR-style 'what would bump if I merged this branch'
    queries (``since=origin/main``) or for inspecting a different window
    (``since=HEAD~10``). The *current* version resolution (latest tag,
    bump_file, initial_version) is unaffected - only the commit window
    moves.
    """
    matcher = ComponentMatcher(config.components)
    plan = Plan()
    versions = {name: _current_version(repo, config, name) for name in config.components}

    _direct_pass(repo, config, matcher, plan, versions, since_override=since)
    _triggers_pass(config, plan, versions)
    _mirror_pass(config, matcher, plan, versions)

    if pre is not None or finalize:
        for bump in plan.bumps.values():
            bump.pre = pre
            bump.finalize = finalize

    # `--finalize` is a release event in its own right - allow finalising a
    # pre-release component even when no new commits landed since the rc tag.
    if finalize:
        for name in config.components:
            current = versions[name]
            if current.is_prerelease and name not in plan.bumps:
                plan.bumps[name] = PlannedBump(
                    component=name,
                    current=current,
                    kind="patch",
                    reasons=[ManualReason("explicit --finalize")],
                    finalize=True,
                )

    # --force applies after every other pass so it composes with --pre,
    # --finalize, triggers and mirrors. The forced kind is promoted into
    # any existing bump (never demoted) and adds a ManualReason for
    # auditability.
    if force:
        for name, kind in force.items():
            if name not in config.components:
                continue
            reason = ManualReason(f"--force {name}:{kind}")
            existing = plan.bumps.get(name)
            if existing is None:
                plan.bumps[name] = PlannedBump(
                    component=name,
                    current=versions[name],
                    kind=kind,
                    reasons=[reason],
                    pre=pre,
                    finalize=finalize,
                )
            else:
                stronger = _stronger(existing.kind, kind)
                if stronger != existing.kind:
                    existing.kind = stronger  # type: ignore[assignment]
                if reason not in existing.reasons:
                    existing.reasons.append(reason)

    # Apply per-component version_scheme so .next renders correctly.
    for name, bump in plan.bumps.items():
        bump.scheme = config.components[name].version_scheme

    return plan
