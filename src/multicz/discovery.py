"""Repo-aware initial config generation.

Walks the working tree once and proposes a :class:`Config` populated with one
:class:`Component` per detected manifest. Component names come from the
manifest itself (``[project].name`` in ``pyproject.toml``, ``name`` in each
``Chart.yaml`` and the root ``package.json``) so the generated tags read
naturally (``multicz-v1.3.0`` rather than ``api-v1.3.0``).

``Chart.yaml`` is searched recursively across the whole repo (excluding
common noise directories like ``node_modules`` or ``.venv``) so charts
under ``helm/``, ``deploy/``, ``infra/``, or any other layout are picked
up. When multiple charts coexist with one python project, the auto-mirror
only wires charts whose ``name`` matches the python project, so a
``worker`` chart next to an ``api`` service stays independent. A single
chart + single python project always pairs unambiguously.

Paths only include files whose change clearly warrants a version bump:
``Dockerfile`` is included when present (new base image / RUN step = new
artifact), but ``.dockerignore`` is not — it almost always signals
build-context hygiene rather than an artifact change.
"""

from __future__ import annotations

import json
from pathlib import Path

import tomlkit
from ruamel.yaml import YAML

from .config import Component, FileKey


def _read_pyproject_name(path: Path) -> str | None:
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    project = doc.get("project")
    if not isinstance(project, dict):
        return None
    name = project.get("name")
    return str(name) if name else None


def _read_chart_name(path: Path) -> str | None:
    try:
        data = YAML(typ="safe").load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    name = data.get("name")
    return str(name) if name else None


def _read_package_json_name(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    name = data.get("name")
    if not name:
        return None
    # npm scopes (@scope/pkg) are not valid TOML table keys without quoting and
    # produce ugly tags; prefer the unscoped portion.
    return str(name).split("/", 1)[-1]


def _unique(name: str, taken: set[str], suffix: str) -> str:
    if name not in taken:
        return name
    candidate = f"{name}-{suffix}"
    counter = 2
    while candidate in taken:
        candidate = f"{name}-{suffix}-{counter}"
        counter += 1
    return candidate


# Directories never recursed into when scanning for manifests.
_NOISE_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", ".venv", "venv", ".tox", ".nox",
    "vendor", "third_party",
    "target", "build", "dist",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
})


def _find_chart_yamls(repo: Path) -> list[Path]:
    """Return every ``Chart.yaml`` under ``repo`` outside common noise dirs."""
    found: list[Path] = []
    for path in repo.rglob("Chart.yaml"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo).parts
        if any(part in _NOISE_DIRS for part in rel_parts):
            continue
        found.append(path)
    return sorted(found)


def discover_components(repo: Path) -> dict[str, Component]:
    """Return a fresh component map populated from manifests found under ``repo``."""
    components: dict[str, Component] = {}
    python_name: str | None = None

    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        name = _read_pyproject_name(pyproject) or "app"
        paths = ["pyproject.toml"]
        if (repo / "src").is_dir():
            paths.insert(0, "src/**")
        if (repo / "tests").is_dir():
            paths.append("tests/**")
        if (repo / "Dockerfile").is_file():
            paths.append("Dockerfile")
        components[name] = Component(
            paths=paths,
            bump_files=[FileKey(file=Path("pyproject.toml"), key="project.version")],
            changelog=Path("CHANGELOG.md"),
        )
        python_name = name

    chart_names: list[str] = []
    chart_raw_names: dict[str, str] = {}  # comp_name -> raw chart name (for matching)
    for chart_yaml in _find_chart_yamls(repo):
        chart_dir = chart_yaml.parent
        rel_dir = chart_dir.relative_to(repo).as_posix()
        rel_chart = chart_yaml.relative_to(repo)
        raw = _read_chart_name(chart_yaml) or chart_dir.name
        comp_name = _unique(raw, set(components), suffix="chart")
        components[comp_name] = Component(
            paths=[f"{rel_dir}/**"],
            bump_files=[FileKey(file=rel_chart, key="version")],
            changelog=Path(f"{rel_dir}/CHANGELOG.md"),
        )
        chart_names.append(comp_name)
        chart_raw_names[comp_name] = raw

    if python_name and chart_names:
        py = components[python_name]
        # Single chart + single python project: unambiguous, mirror.
        # Multiple charts: only mirror to the chart(s) whose name matches the
        # python project, so a 'worker' chart next to an 'api' python project
        # stays independent.
        candidates = (
            chart_names if len(chart_names) == 1
            else [n for n in chart_names if chart_raw_names[n] == python_name]
        )
        for chart_comp_name in candidates:
            chart_yaml_path = components[chart_comp_name].bump_files[0].file
            py.mirrors.append(FileKey(file=chart_yaml_path, key="appVersion"))

    package_json = repo / "package.json"
    if package_json.is_file():
        name = _read_package_json_name(package_json)
        if name:
            comp_name = _unique(name, set(components), suffix="js")
            paths = ["package.json"]
            # only claim src/** for the JS app if there's no Python project to do it
            if python_name is None and (repo / "src").is_dir():
                paths.insert(0, "src/**")
            components[comp_name] = Component(
                paths=paths,
                bump_files=[FileKey(file=Path("package.json"), key="version")],
                changelog=Path("CHANGELOG.md") if python_name is None else None,
            )

    return components


def render_config(
    components: dict[str, Component],
    *,
    initial_version: str = "0.1.0",
    tag_format: str = "{component}-v{version}",
) -> str:
    """Render a ``multicz.toml`` document from a component map."""
    doc = tomlkit.document()
    doc.add(tomlkit.comment("multicz.toml — generated by `multicz init`"))
    doc.add(tomlkit.comment("https://github.com/goabonga/multicz"))
    doc.add(tomlkit.nl())

    project = tomlkit.table()
    project["commit_convention"] = "conventional"
    project["tag_format"] = tag_format
    project["initial_version"] = initial_version
    doc["project"] = project

    components_root = tomlkit.table(is_super_table=True)
    for name, comp in components.items():
        section = tomlkit.table()
        section["paths"] = list(comp.paths)
        if comp.exclude_paths:
            section["exclude_paths"] = list(comp.exclude_paths)
        if comp.bump_files:
            section["bump_files"] = _filekey_array(comp.bump_files)
        if comp.mirrors:
            section["mirrors"] = _filekey_array(comp.mirrors)
        if comp.triggers:
            section["triggers"] = list(comp.triggers)
        if comp.changelog is not None:
            section["changelog"] = str(comp.changelog)
        components_root.append(name, section)
    doc.append("components", components_root)

    return tomlkit.dumps(doc)


def _inline_filekey(fk: FileKey):
    inline = tomlkit.inline_table()
    inline["file"] = str(fk.file)
    if fk.key is not None:
        inline["key"] = fk.key
    return inline


def _filekey_array(items: list[FileKey]):
    array = tomlkit.array()
    array.multiline(True)
    for fk in items:
        array.append(_inline_filekey(fk))
    return array
