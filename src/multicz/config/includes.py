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

A component file may also carry ``[plugins.<name>]`` tables, merged into
the root's: a plugin option that belongs to one component can then live
next to it. Tables merge key by key, and a value set twice, in two files
or in a file and the root, is an error naming both.

Things deliberately not rebased: ``post_bump`` commands (opaque shell,
always run from the repository root), plugin options (opaque to multicz,
so any path in them stays relative to the repository root) and the
project-wide settings, which only the root may declare.
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

    plugins = _plain_copy(raw.get("plugins") or {})
    plugin_origin: dict[tuple[str, ...], str] = {}
    _record_leaves(plugins, (), "the root config", plugin_origin)

    files = find_component_files(patterns, root)
    for file in files:
        rel = file.relative_to(root).as_posix()
        base = PurePosixPath(rel).parent.as_posix()
        base = "" if base == "." else base
        declared, file_plugins = _read_component_file(file, rel)
        _merge_plugins(plugins, file_plugins, (), rel, plugin_origin)
        for name, body in declared.items():
            if name in origin:
                raise ValueError(f"component {name!r} is declared in both {origin[name]} and {rel}")
            origin[name] = rel
            components[name] = _rebase_component(body, base, rel)
            _check_component(name, components[name], rel)
    merged = {**raw, "components": components}
    if plugins:
        merged["plugins"] = plugins
    return merged, files


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


def _read_component_file(file: Path, rel: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """The components and the plugin tables a component file declares."""
    try:
        data = tomlkit.parse(file.read_text(encoding="utf-8")).unwrap()
    except Exception as exc:
        raise ValueError(f"{rel}: cannot be read as TOML: {exc}") from exc
    extra = sorted(set(data) - {"components", "plugins"})
    if extra:
        raise ValueError(
            f"{rel}: only [components] and [plugins] may be declared in a component file, "
            f"found: {', '.join(extra)}"
        )
    table = data.get("components") or {}
    if isinstance(table, list):
        table = components_table(table)
    if not table:
        raise ValueError(f"{rel}: declares no component")
    plugins = data.get("plugins") or {}
    if not isinstance(plugins, dict) or not all(isinstance(v, dict) for v in plugins.values()):
        raise ValueError(f"{rel}: [plugins] must hold one table per plugin")
    return table, plugins


def _plain_copy(value: Any) -> Any:
    """A copy made of plain dicts and lists, safe to merge into."""
    if isinstance(value, dict):
        return {key: _plain_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_copy(item) for item in value]
    return value


def _record_leaves(
    table: dict[str, Any], prefix: tuple[str, ...], origin: str, seen: dict[tuple[str, ...], str]
) -> None:
    for key, value in table.items():
        if isinstance(value, dict):
            _record_leaves(value, (*prefix, key), origin, seen)
        else:
            seen[(*prefix, key)] = origin


def _merge_plugins(
    target: dict[str, Any],
    incoming: dict[str, Any],
    prefix: tuple[str, ...],
    rel: str,
    origin: dict[tuple[str, ...], str],
) -> None:
    """Merge ``incoming`` into ``target`` key by key; a value set twice is an error."""
    for key, value in incoming.items():
        where = (*prefix, key)
        if isinstance(value, dict) and isinstance(target.get(key, {}), dict):
            _merge_plugins(target.setdefault(key, {}), value, where, rel, origin)
        elif key in target:
            first = origin.get(where, "the root config")
            raise ValueError(f"plugins.{'.'.join(where)} is declared in both {first} and {rel}")
        else:
            target[key] = _plain_copy(value)
            origin[where] = rel


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
