"""Configuration and repository sanity checks for multicz.

The :func:`validate` function runs every check and returns a flat list of
:class:`Finding`s. Each finding has a level (``error``, ``warning``,
``info``), a stable ``check`` identifier, an optional component name,
and a human-readable message. The CLI ``multicz validate`` command
exits non-zero when any error is reported (and when ``--strict`` is
passed, also when any warning is).
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pathspec

from .components import ComponentMatcher
from .config import Config

Level = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Finding:
    level: Level
    check: str
    component: str | None
    message: str

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "check": self.check,
            "component": self.component,
            "message": self.message,
        }


def validate(repo: Path, config: Config) -> list[Finding]:
    """Run every sanity check and return a flat list of findings."""
    findings: list[Finding] = []
    matcher = ComponentMatcher(config.components)

    findings.extend(_check_bump_files_exist(repo, config))
    findings.extend(_check_path_overlaps(repo, config))
    findings.extend(_check_mirror_targets(config, matcher))
    findings.extend(_check_trigger_cycles(config))
    findings.extend(_check_mirror_cycles(config, matcher))
    findings.extend(_check_changelog_paths(repo, config))
    findings.extend(_check_current_versions(repo, config))
    findings.extend(_check_debian_changelogs(repo, config))
    return findings


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------


def _check_bump_files_exist(repo: Path, config: Config) -> Iterator[Finding]:
    for name, comp in config.components.items():
        for fk in comp.bump_files:
            path = repo / fk.file
            if not path.is_file():
                yield Finding(
                    level="error",
                    check="bump_files_exist",
                    component=name,
                    message=f"bump_file {fk.file.as_posix()!r} does not exist",
                )


def _check_path_overlaps(repo: Path, config: Config) -> Iterator[Finding]:
    """Detect when multiple components claim the same file.

    The reported level — and whether the finding is reported at all —
    depends on ``project.overlap_policy``:

    * ``error`` (default): refuse to plan/bump until the user resolves
      the overlap. Most predictable for newcomers.
    * ``first-match``: surface as a warning. The first-declared
      component wins, the others silently lose. Backwards-compatible
      with multicz before this knob existed.
    * ``allow``: same runtime behavior as ``first-match`` but the
      finding is suppressed (you've explicitly accepted the overlap).
    * ``all``: surface as info. A shared file bumps every claiming
      component (see :meth:`ComponentMatcher.match_all`).
    """
    policy = config.project.overlap_policy
    if policy == "allow":
        return

    files = _list_tracked_files(repo)
    if not files:
        return

    includes = {
        name: pathspec.PathSpec.from_lines("gitignore", comp.paths)
        for name, comp in config.components.items()
    }
    excludes = {
        name: pathspec.PathSpec.from_lines("gitignore", comp.exclude_paths)
        for name, comp in config.components.items()
    }

    seen: dict[tuple[str, str], str] = {}
    for f in files:
        owners = [
            n
            for n in config.components
            if includes[n].match_file(f) and not excludes[n].match_file(f)
        ]
        if len(owners) <= 1:
            continue
        winner = owners[0]
        for loser in owners[1:]:
            seen.setdefault((winner, loser), f)

    if not seen:
        return

    level: Level
    if policy == "error":
        level = "error"
        suffix = (
            "Set overlap_policy = 'first-match', 'allow', or 'all' to "
            "accept it, or tighten the paths / add an exclude_paths entry."
        )
    elif policy == "first-match":
        level = "warning"
        suffix = (
            "first-match-wins means the earlier-declared component owns "
            "the shared files."
        )
    else:  # all
        level = "info"
        suffix = (
            "overlap_policy = 'all' is in effect — every claiming "
            "component bumps when the shared file changes."
        )

    for (winner, loser), sample in seen.items():
        yield Finding(
            level=level,
            check="path_overlap",
            component=loser,
            message=(
                f"shares files with {winner!r} (e.g. {sample!r}). {suffix}"
            ),
        )


def _check_mirror_targets(
    config: Config, matcher: ComponentMatcher
) -> Iterator[Finding]:
    for name, comp in config.components.items():
        for mirror in comp.mirrors:
            target = matcher.match(str(mirror.file))
            if target is None:
                yield Finding(
                    level="info",
                    check="mirror_target_unowned",
                    component=name,
                    message=(
                        f"mirror target {str(mirror.file)!r} is not owned by "
                        "any component; the version is written but no cascade "
                        "fires"
                    ),
                )
            elif target == name:
                yield Finding(
                    level="warning",
                    check="mirror_self_target",
                    component=name,
                    message=(
                        f"mirror target {str(mirror.file)!r} resolves back to "
                        "this component; you probably want a bump_files entry "
                        "instead of a mirror"
                    ),
                )


def _check_trigger_cycles(config: Config) -> Iterator[Finding]:
    # Edge: upstream -> downstream (downstream lists upstream in triggers)
    graph: dict[str, list[str]] = {n: [] for n in config.components}
    for name, comp in config.components.items():
        for upstream in comp.triggers:
            if upstream in graph:
                graph[upstream].append(name)

    cycle = _find_cycle(graph)
    if cycle is not None:
        yield Finding(
            level="error",
            check="trigger_cycle",
            component=None,
            message=f"trigger cycle: {' -> '.join([*cycle, cycle[0]])}",
        )


def _check_mirror_cycles(
    config: Config, matcher: ComponentMatcher
) -> Iterator[Finding]:
    # Edge: A -> B when A's mirror writes into a path owned by B
    graph: dict[str, list[str]] = {n: [] for n in config.components}
    for name, comp in config.components.items():
        for mirror in comp.mirrors:
            target = matcher.match(str(mirror.file))
            if target is not None and target != name and target not in graph[name]:
                graph[name].append(target)

    cycle = _find_cycle(graph)
    if cycle is not None:
        yield Finding(
            level="error",
            check="mirror_cycle",
            component=None,
            message=f"mirror cascade cycle: {' -> '.join([*cycle, cycle[0]])}",
        )


def _check_changelog_paths(repo: Path, config: Config) -> Iterator[Finding]:
    for name, comp in config.components.items():
        if comp.changelog is None:
            continue
        path = repo / comp.changelog
        if path.exists() and not path.is_file():
            yield Finding(
                level="error",
                check="changelog_not_a_file",
                component=name,
                message=(
                    f"changelog path {str(comp.changelog)!r} exists but is "
                    "not a regular file"
                ),
            )


def _check_current_versions(repo: Path, config: Config) -> Iterator[Finding]:
    from .planner import _current_version

    for name in config.components:
        try:
            _current_version(repo, config, name)
        except Exception as exc:
            yield Finding(
                level="error",
                check="version_unreadable",
                component=name,
                message=f"could not resolve current version: {exc}",
            )


def _check_debian_changelogs(repo: Path, config: Config) -> Iterator[Finding]:
    from .debian import parse_top_stanza

    for name, comp in config.components.items():
        if comp.format != "debian" or comp.debian is None:
            continue
        path = repo / comp.debian.changelog
        if not path.exists():
            yield Finding(
                level="info",
                check="debian_changelog_missing",
                component=name,
                message=(
                    f"{str(comp.debian.changelog)!r} does not exist; "
                    "it will be created on the first bump"
                ),
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            yield Finding(
                level="error",
                check="debian_changelog_unreadable",
                component=name,
                message=f"could not read {str(comp.debian.changelog)!r}: {exc}",
            )
            continue
        if parse_top_stanza(text) is None:
            yield Finding(
                level="error",
                check="debian_changelog_unparseable",
                component=name,
                message=(
                    f"{str(comp.debian.changelog)!r} top stanza is not a "
                    "valid Debian changelog header"
                ),
            )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _list_tracked_files(repo: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


_WHITE, _GRAY, _BLACK = 0, 1, 2


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Iterative DFS cycle finder. Returns the cycle nodes or ``None``."""
    color = dict.fromkeys(graph, _WHITE)

    def dfs(start: str) -> list[str] | None:
        stack: list[tuple[str, Iterable[str], list[str]]] = [
            (start, iter(graph.get(start, [])), [start])
        ]
        color[start] = _GRAY
        while stack:
            node, neighbors, path = stack[-1]
            try:
                nxt = next(neighbors)
            except StopIteration:
                color[node] = _BLACK
                stack.pop()
                continue
            if nxt not in color:
                continue
            if color[nxt] == _GRAY:
                idx = path.index(nxt)
                return path[idx:]
            if color[nxt] == _WHITE:
                color[nxt] = _GRAY
                stack.append((nxt, iter(graph.get(nxt, [])), [*path, nxt]))
        return None

    for node in graph:
        if color[node] == _WHITE:
            result = dfs(node)
            if result:
                return result
    return None
