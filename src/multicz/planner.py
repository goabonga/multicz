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

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from packaging.version import InvalidVersion, Version

from .commits import (
    BumpKind,
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


# PEP 440 normalises 'a'/'b'/'c' into 'alpha'/'beta'/'rc' shapes; we keep a
# dictionary of common aliases so 1.3.0-rc.1 and 1.3.0-c.1 collapse to the
# same cycle.
_PRE_ALIASES = {"a": "alpha", "b": "beta", "c": "rc", "pre": "rc", "preview": "rc"}


def _norm_pre_label(label: str) -> str:
    label = label.lower()
    return _PRE_ALIASES.get(label, label)


def compute_next(
    current: Version,
    kind: BumpKind,
    *,
    pre: str | None = None,
    finalize: bool = False,
) -> str:
    """Compute the next version string given ``kind`` and optional pre-release flags.

    The result is rendered in a *semver-friendly* form (``1.3.0-rc.1``) so
    it lands cleanly into ``pyproject.toml``, ``package.json`` and
    ``Cargo.toml`` alike — :class:`packaging.version.Version` parses both
    semver and PEP 440 spellings, so ordering is preserved.

    Behavior matrix:

    +-------------+----------+-----------+------------------+----------------------+
    | current     | --pre    | --finalize| result           | meaning              |
    +-------------+----------+-----------+------------------+----------------------+
    | 1.2.3       | None     | False     | 1.3.0            | regular bump (feat)  |
    | 1.2.3       | rc       | False     | 1.3.0-rc.1       | enter RC cycle       |
    | 1.3.0-rc.1  | None     | False     | 1.3.0            | auto-finalize        |
    | 1.3.0-rc.1  | None     | True      | 1.3.0            | explicit finalize    |
    | 1.3.0-rc.1  | rc       | False     | 1.3.0-rc.2       | next RC              |
    | 1.3.0-rc.1  | beta     | False     | 1.3.0-beta.1     | switch label         |
    +-------------+----------+-----------+------------------+----------------------+
    """
    base = f"{current.major}.{current.minor}.{current.micro}"

    if finalize:
        if current.is_prerelease:
            return base
        # Already final: explicit --finalize is a no-op except for kind progression
        bumped = bump_version(current, kind)
        return f"{bumped.major}.{bumped.minor}.{bumped.micro}"

    if pre is None:
        if current.is_prerelease:
            # Auto-finalize: shipping the in-progress pre-release as the release
            return base
        bumped = bump_version(current, kind)
        return f"{bumped.major}.{bumped.minor}.{bumped.micro}"

    # pre is set: entering or continuing a pre-release cycle
    if current.is_prerelease and current.pre is not None:
        existing = _norm_pre_label(current.pre[0])
        wanted = _norm_pre_label(pre)
        if existing == wanted:
            counter = (current.pre[1] or 0) + 1
            return f"{base}-{pre}.{counter}"
        # Different label, same target version
        return f"{base}-{pre}.1"

    # Currently a final release: bump first, then enter the pre cycle
    target = bump_version(current, kind)
    return f"{target.major}.{target.minor}.{target.micro}-{pre}.1"


@dataclass(frozen=True)
class CommitReason:
    """A planned bump driven by a conventional commit landing on this component."""

    sha: str
    type: str
    scope: str | None
    breaking: bool
    subject: str
    files: tuple[str, ...]  # files matched into THIS component (subset of commit.files)
    bump_kind: BumpKind
    # When ``bump_policy = "scoped"`` demotes this commit's natural kind
    # (e.g. minor -> patch because the scope points at another component),
    # ``original_kind`` records what would have been used otherwise.
    # ``None`` means no demotion happened.
    original_kind: BumpKind | None = None

    def summary(self) -> str:
        bang = "!" if self.breaking else ""
        scope = f"({self.scope})" if self.scope else ""
        head = f"{self.sha[:7]} {self.type}{scope}{bang}: {self.subject}"
        if self.original_kind is not None:
            head += f" [demoted: {self.original_kind} -> {self.bump_kind}]"
        return head

    def to_dict(self) -> dict:
        return {
            "kind": "commit",
            "sha": self.sha,
            "type": self.type,
            "scope": self.scope,
            "breaking": self.breaking,
            "subject": self.subject,
            "files": list(self.files),
            "bump_kind": self.bump_kind,
            "original_kind": self.original_kind,
        }


@dataclass(frozen=True)
class TriggerReason:
    """A planned bump cascaded from a declared upstream component."""

    upstream: str
    upstream_kind: BumpKind

    def summary(self) -> str:
        return f"triggered by {self.upstream} ({self.upstream_kind})"

    def to_dict(self) -> dict:
        return {
            "kind": "trigger",
            "upstream": self.upstream,
            "upstream_kind": self.upstream_kind,
        }


@dataclass(frozen=True)
class MirrorReason:
    """A planned bump cascaded from a mirror writing into this component's path."""

    upstream: str
    file: str
    key: str | None

    def summary(self) -> str:
        target = self.file if self.key is None else f"{self.file}:{self.key}"
        return f"mirror cascade from {self.upstream} ({target})"

    def to_dict(self) -> dict:
        return {
            "kind": "mirror",
            "upstream": self.upstream,
            "file": self.file,
            "key": self.key,
        }


@dataclass(frozen=True)
class ManualReason:
    """A planned bump that came from a CLI flag (``--finalize``, force-bump,
    …) rather than a commit, trigger, or mirror."""

    note: str

    def summary(self) -> str:
        return self.note

    def to_dict(self) -> dict:
        return {"kind": "manual", "note": self.note}


Reason = CommitReason | TriggerReason | MirrorReason | ManualReason


@dataclass
class PlannedBump:
    component: str
    current: Version
    kind: BumpKind
    reasons: list[Reason] = field(default_factory=list)
    pre: str | None = None
    finalize: bool = False

    @property
    def next(self) -> str:
        """The new version, rendered as a semver-friendly string."""
        return compute_next(
            self.current, self.kind, pre=self.pre, finalize=self.finalize
        )

    @property
    def next_version(self) -> Version:
        """Parsed Version of :attr:`next` (for ordering)."""
        return Version(self.next)

    def reason_summaries(self) -> list[str]:
        return [r.summary() for r in self.reasons]


@dataclass
class Plan:
    bumps: dict[str, PlannedBump] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.bumps)

    def __iter__(self):
        return iter(self.bumps.values())


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
         or the top stanza of ``debian/changelog`` for debian-format
         components,
      3. ``initial_version`` from the project settings (bootstrap).
    """
    prefix = tag_prefix(config.tag_format_for(name), name)
    tagged = latest_version(repo, prefix)
    if tagged is not None:
        return tagged

    comp = config.components[name]
    if comp.format == "debian" and comp.debian is not None:
        from .debian import from_debian_pre, parse_top_version, upstream_version

        changelog_path = repo / comp.debian.changelog
        if changelog_path.is_file():
            try:
                top = parse_top_version(
                    changelog_path.read_text(encoding="utf-8")
                )
                if top:
                    return Version(from_debian_pre(upstream_version(top)))
            except (InvalidVersion, OSError):
                pass
        return Version(config.project.initial_version)

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
    overlap_all = config.project.overlap_policy == "all"
    for name in config.components:
        prefix = tag_prefix(config.tag_format_for(name), name)
        since = latest_tag(repo, prefix)
        ignored = config.ignored_types_for(name)
        for commit in commits_since(repo, since):
            header = (
                f"{commit.type}({commit.scope}): {commit.subject}"
                if commit.scope
                else f"{commit.type}: {commit.subject}"
            )
            if release_re.match(header):
                continue
            if commit.type.lower() in ignored:
                continue
            if commit.bump_kind is None:
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
            kind = commit.bump_kind
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
                original_kind=commit.bump_kind if demoted else None,
            )
            _promote(plan, name, kind, versions[name], reason)


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
                reason = TriggerReason(
                    upstream=upstream,
                    upstream_kind=upstream_bump.kind,
                )
                if _promote(
                    plan,
                    name,
                    upstream_bump.kind,
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
) -> Plan:
    """Compute the bump plan for ``repo`` against ``config``.

    Pass ``pre="rc"`` (or ``"alpha"``, ``"beta"``, …) to drive a release
    candidate cycle, or ``finalize=True`` to drop a pre-release suffix.
    Both flags apply to *every* bumping component in the plan.
    """
    matcher = ComponentMatcher(config.components)
    plan = Plan()
    versions = {name: _current_version(repo, config, name) for name in config.components}

    _direct_pass(repo, config, matcher, plan, versions)
    _triggers_pass(config, plan, versions)
    _mirror_pass(config, matcher, plan, versions)

    if pre is not None or finalize:
        for bump in plan.bumps.values():
            bump.pre = pre
            bump.finalize = finalize

    # `--finalize` is a release event in its own right — allow finalising a
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

    return plan
