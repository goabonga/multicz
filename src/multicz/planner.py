"""Compute the bump plan for every component declared in the config.

The planner is split into three passes:

1. **Direct**: each component looks at the commits made since its own last
   tag, keeps those whose changed files map back to it, and aggregates the
   strongest bump kind implied by the conventional commit headers.
2. **Triggers**: a component declared in another's ``triggers`` list inherits
   that upstream's bump kind (clamped to at least patch).
3. **Mirror cascade**: if component A writes its version into a file owned by
   component B (a ``mirror``), B receives a patch bump — keeping Helm chart
   immutability (option A from the design discussion).

All three passes share a single :func:`_promote` helper so a component can be
upgraded (e.g. patch → minor) but never downgraded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from packaging.version import Version

from packaging.version import InvalidVersion

from .commits import (
    BumpKind,
    Commit,
    commits_since,
    latest_tag,
    latest_version,
    tag_prefix,
)
from .components import ComponentMatcher
from .config import Config
from .writers import WriterError, read_value

_KIND_ORDER: dict[BumpKind, int] = {"patch": 1, "minor": 2, "major": 3}


def _stronger(a: BumpKind | None, b: BumpKind | None) -> BumpKind | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if _KIND_ORDER[a] >= _KIND_ORDER[b] else b


def aggregate_kind(kinds: Iterable[BumpKind | None]) -> BumpKind | None:
    result: BumpKind | None = None
    for kind in kinds:
        result = _stronger(result, kind)
    return result


def bump_version(version: Version, kind: BumpKind) -> Version:
    major, minor, patch = version.major, version.minor, version.micro
    if kind == "major":
        return Version(f"{major + 1}.0.0")
    if kind == "minor":
        return Version(f"{major}.{minor + 1}.0")
    return Version(f"{major}.{minor}.{patch + 1}")


@dataclass
class PlannedBump:
    component: str
    current: Version
    kind: BumpKind
    reasons: list[str] = field(default_factory=list)

    @property
    def next(self) -> Version:
        return bump_version(self.current, self.kind)


@dataclass
class Plan:
    bumps: dict[str, PlannedBump] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.bumps)

    def __iter__(self):
        return iter(self.bumps.values())


def _commit_summary(commit: Commit) -> str:
    bang = "!" if commit.breaking else ""
    scope = f"({commit.scope})" if commit.scope else ""
    return f"{commit.sha[:7]} {commit.type}{scope}{bang}: {commit.subject}"


def _promote(
    plan: Plan,
    component: str,
    kind: BumpKind,
    current: Version,
    reason: str,
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
      3. ``initial_version`` from the project settings (bootstrap).
    """
    prefix = tag_prefix(config.project.tag_format, name)
    tagged = latest_version(repo, prefix)
    if tagged is not None:
        return tagged

    comp = config.components[name]
    if comp.bump_files:
        primary = comp.bump_files[0]
        try:
            return Version(read_value(repo / primary.file, primary.key))
        except (WriterError, InvalidVersion, FileNotFoundError):
            pass
    return Version(config.project.initial_version)


def _direct_pass(
    repo: Path,
    config: Config,
    matcher: ComponentMatcher,
    plan: Plan,
    versions: dict[str, Version],
) -> None:
    import re

    release_re = re.compile(config.project.release_commit_pattern)
    for name in config.components:
        prefix = tag_prefix(config.project.tag_format, name)
        since = latest_tag(repo, prefix)
        for commit in commits_since(repo, since):
            header = (
                f"{commit.type}({commit.scope}): {commit.subject}"
                if commit.scope
                else f"{commit.type}: {commit.subject}"
            )
            if release_re.match(header):
                continue
            if commit.bump_kind is None:
                continue
            if not any(matcher.match(path) == name for path in commit.files):
                continue
            _promote(plan, name, commit.bump_kind, versions[name], _commit_summary(commit))


def _triggers_pass(
    config: Config, plan: Plan, versions: dict[str, Version]
) -> None:
    changed = True
    while changed:
        changed = False
        for name, comp in config.components.items():
            for upstream in comp.triggers:
                upstream_bump = plan.bumps.get(upstream)
                if upstream_bump is None:
                    continue
                if _promote(
                    plan,
                    name,
                    upstream_bump.kind,
                    versions[name],
                    f"triggered by {upstream}",
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
                if _promote(
                    plan,
                    target,
                    "patch",
                    versions[target],
                    f"mirror cascade from {name}",
                ):
                    changed = True


def build_plan(repo: Path, config: Config) -> Plan:
    matcher = ComponentMatcher(config.components)
    plan = Plan()
    versions = {name: _current_version(repo, config, name) for name in config.components}

    _direct_pass(repo, config, matcher, plan, versions)
    _triggers_pass(config, plan, versions)
    _mirror_pass(config, matcher, plan, versions)
    return plan
