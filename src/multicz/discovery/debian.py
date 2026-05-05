# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Debian ecosystem discovery (``debian/changelog``).

Currently exposed as a post-pass free function (:func:`_detect_debian`)
rather than a regular discovery strategy because its output depends on
what other ecosystems already claimed (the source-layout heuristic).
Stage 4 will move this behind a relation/strategy protocol.
"""

from __future__ import annotations

from pathlib import Path

from ..changelog import parse_top_stanza
from ..config import Component, DebianSettings


def _detect_debian(repo: Path, components: dict[str, Component]) -> None:
    """When ``debian/changelog`` exists, register a format='debian' component
    named after the package declared on the top stanza."""
    changelog = repo / "debian" / "changelog"
    if not changelog.is_file():
        return
    try:
        text = changelog.read_text(encoding="utf-8")
    except OSError:
        return
    stanza = parse_top_stanza(text)
    if stanza is None:
        return
    raw_name = stanza.package
    comp_name = _debian_unique(raw_name, set(components))
    paths = ["debian/**"]
    if (repo / "src").is_dir():
        paths.append("src/**")
    components[comp_name] = Component(
        paths=paths,
        format="debian",
        debian=DebianSettings(),
    )


def _debian_unique(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    candidate = f"{name}-deb"
    counter = 2
    while candidate in taken:
        candidate = f"{name}-deb-{counter}"
        counter += 1
    return candidate
