# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Merge component declarations spread over several files into one config.

A root config can list ``[[component.path]]`` entries, each with a
``path`` pattern relative to its directory::

    [[component.path]]
    path = "packages/*"

Each path selects component files named :data:`COMPONENT_FILENAME`. A
pattern naming a directory (or matching one) selects the file inside it;
a pattern that wildcards over files only selects files carrying that
name, and dot-directories are never walked. A pattern without wildcards
must exist.

A component file holds ``[components.<name>]`` tables, exactly as in the
root. Every path in it is relative to *its own directory* and is rebased
onto the repository root here, so the rest of multicz keeps seeing one
flat :class:`~multicz.config.Config` with repo-relative paths. Names and
``depends_on`` stay global: a component can depend on one declared in
another file.

Two things are deliberately not rebased: ``post_bump`` commands (opaque
shell, always run from the repository root) and the project-wide
settings, which only the root may declare.
"""

from __future__ import annotations

import posixpath
from pathlib import Path, PurePosixPath
from typing import Any

import tomlkit
from pydantic import ValidationError

from .models import Component, ComponentSources, components_table

COMPONENT_FILENAME = "multicz.component.toml"

_GLOB_CHARS = frozenset("*?[")
_DEFAULT_PATHS = ["**"]
_DEFAULT_DEBIAN_CHANGELOG = "debian/changelog"


def resolve_includes(raw: dict[str, Any], root: Path) -> tuple[dict[str, Any], list[Path]]:
    """Return ``raw`` with the included components merged in, and the files read.

    ``raw`` is returned untouched, with no files, when it has no
    ``[[component.path]]`` entry.
    """
    if "component" not in raw:
        return raw, []
    try:
        sources = ComponentSources.model_validate(raw["component"])
    except ValidationError as exc:
        details = "; ".join(
            f"component -> {' -> '.join(str(p) for p in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ValueError(details) from exc
    patterns = [entry.path for entry in sources.path]
    if not patterns:
        return raw, []

    components = raw.get("components") or {}
    if isinstance(components, list):
        components = components_table(components)
    components = dict(components)
    origin = dict.fromkeys(components, "the root config")

    files = find_component_files(patterns, root)
    for file in files:
        rel = file.relative_to(root).as_posix()
        base = PurePosixPath(rel).parent.as_posix()
        base = "" if base == "." else base
        for name, body in _read_components(file, rel).items():
            if name in origin:
                raise ValueError(f"component {name!r} is declared in both {origin[name]} and {rel}")
            origin[name] = rel
            components[name] = _rebase_component(body, base, rel)
            _check_component(name, components[name], rel)
    return {**raw, "components": components}, files


def find_component_files(patterns: list[str], root: Path) -> list[Path]:
    """Expand ``patterns`` into component files, sorted by repo-relative path."""
    found: set[Path] = set()
    for pattern in patterns:
        text = pattern.strip().rstrip("/")
        parts = PurePosixPath(text).parts
        if not text or PurePosixPath(text).is_absolute() or ".." in parts:
            raise ValueError(f"component path {pattern!r} must be a path inside the repository")
        if _GLOB_CHARS.isdisjoint(text):
            found.add(_literal(root, text, pattern))
            continue
        for match in root.glob(text):
            if any(part.startswith(".") for part in match.relative_to(root).parts):
                continue
            if match.is_dir():
                candidate = match / COMPONENT_FILENAME
                if candidate.is_file():
                    found.add(candidate)
            elif match.name == COMPONENT_FILENAME:
                found.add(match)
    return sorted(found, key=lambda p: p.relative_to(root).as_posix())


def _literal(root: Path, text: str, pattern: str) -> Path:
    target = root / text
    if target.is_dir():
        target = target / COMPONENT_FILENAME
    if not target.is_file():
        raise ValueError(f"component path {pattern!r}: no such file {target.relative_to(root)}")
    return target


def _read_components(file: Path, rel: str) -> dict[str, dict[str, Any]]:
    try:
        data = tomlkit.parse(file.read_text(encoding="utf-8")).unwrap()
    except Exception as exc:
        raise ValueError(f"{rel}: cannot be read as TOML: {exc}") from exc
    extra = sorted(set(data) - {"components"})
    if extra:
        raise ValueError(
            f"{rel}: only [components] may be declared in a component file, found: "
            f"{', '.join(extra)}"
        )
    table = data.get("components") or {}
    if isinstance(table, list):
        table = components_table(table)
    if not table:
        raise ValueError(f"{rel}: declares no component")
    return table


def _check_component(name: str, body: dict[str, Any], rel: str) -> None:
    """Validate on its own so the error names the file it came from."""
    try:
        Component.model_validate(body)
    except ValidationError as exc:
        details = "; ".join(
            f"{' -> '.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ValueError(f"{rel}: component {name!r}: {details}") from exc


def _rebase_component(body: dict[str, Any], base: str, rel: str) -> dict[str, Any]:
    out = dict(body)
    out["paths"] = [_anchor(p, base, rel) for p in body.get("paths", _DEFAULT_PATHS)]
    if "exclude_paths" in body:
        out["exclude_paths"] = [_anchor(p, base, rel) for p in body["exclude_paths"]]
    if body.get("changelog") is not None:
        out["changelog"] = _join(base, str(body["changelog"]), rel)
    for key in ("bump_files", "mirrors"):
        if key in body:
            out[key] = [_rebase_file(entry, base, rel) for entry in body[key]]
    if "writers" in body:
        out["writers"] = [_rebase_writer(w, base, rel) for w in body["writers"]]
    return out


def _rebase_file(entry: Any, base: str, rel: str) -> Any:
    if not isinstance(entry, dict) or "file" not in entry:
        return entry
    return {**entry, "file": _join(base, str(entry["file"]), rel)}


def _rebase_writer(writer: Any, base: str, rel: str) -> Any:
    if not isinstance(writer, dict):
        return writer
    if "file" not in writer and writer.get("type") == "debian-changelog":
        writer = {**writer, "file": _DEFAULT_DEBIAN_CHANGELOG}
    return _rebase_file(writer, base, rel)


def _join(base: str, value: str, rel: str) -> str:
    """Resolve a file path declared in ``rel`` onto the repository root."""
    joined = posixpath.normpath(posixpath.join(base, value))
    if posixpath.isabs(value) or joined == ".." or joined.startswith("../"):
        raise ValueError(f"{rel}: path {value!r} must stay inside the repository")
    return joined


def _anchor(pattern: str, base: str, rel: str) -> str:
    """Rebase a gitignore-style glob so it keeps its meaning under ``base``.

    A pattern with a slash in it is anchored to the declaring directory; one
    without matches at any depth below it, and has to stay that way.
    """
    text = pattern.strip()
    if not base:
        return text
    negated = text.startswith("!")
    body = text[1:] if negated else text
    if body.startswith("./"):
        body = body[2:]
    if ".." in body.split("/"):
        raise ValueError(f"{rel}: pattern {pattern!r} must stay inside its directory")
    anchored = body.startswith("/") or "/" in body.rstrip("/")
    body = body.lstrip("/")
    rebased = f"{base}/{body}" if anchored or body == "**" else f"{base}/**/{body}"
    return f"!{rebased}" if negated else rebased
