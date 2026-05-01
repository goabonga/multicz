"""Repo-aware initial config generation.

Walks the working tree once and proposes a :class:`Config` populated with
one :class:`Component` per detected manifest. Component names come from the
manifest itself (``[project].name`` in ``pyproject.toml``, ``[package].name``
in ``Cargo.toml``, the last segment of ``module …`` in ``go.mod``, ``name``
in ``Chart.yaml`` and ``package.json``, etc.).

Recognised manifests (all searched recursively, except where noted):

* Python — ``pyproject.toml`` at repo root
* Helm — every ``Chart.yaml``
* Rust — every ``Cargo.toml`` (workspaces with ``[workspace.package].version``
  collapse to a single component; member crates that inherit are skipped)
* Go — every ``go.mod`` (tag-driven, no version file)
* Gradle — root ``gradle.properties`` with a ``version=`` line
* Node.js — ``package.json`` at repo root, with workspace members expanded
  when the root declares ``workspaces`` (or a sibling ``pnpm-workspace.yaml``)

Common noise directories (``.git``, ``node_modules``, ``.venv``, ``target``,
``build``, ``dist``, ``vendor``, …) are excluded.

Paths only include files whose change clearly warrants a version bump:
``Dockerfile`` is included when present, but ``.dockerignore`` is not —
it almost always signals build-context hygiene rather than an artifact
change.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import tomlkit
from ruamel.yaml import YAML

from .config import Component, FileKey

_GRADLE_NAME_RE = re.compile(
    r"rootProject\.name\s*=\s*['\"]([^'\"]+)['\"]"
)


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


def _find_manifests(repo: Path, filename: str) -> list[Path]:
    """Return every ``filename`` under ``repo`` outside noise dirs."""
    found: list[Path] = []
    for path in repo.rglob(filename):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo).parts
        if any(part in _NOISE_DIRS for part in rel_parts):
            continue
        found.append(path)
    return sorted(found)


def _find_chart_yamls(repo: Path) -> list[Path]:
    return _find_manifests(repo, "Chart.yaml")


def _read_gradle_property(path: Path, key: str) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped[0] in "#!":
            continue
        if "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        if k.strip() == key:
            return v.strip()
    return None


def _read_gradle_root_name(repo: Path) -> str | None:
    for filename in ("settings.gradle", "settings.gradle.kts"):
        path = repo / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        match = _GRADLE_NAME_RE.search(text)
        if match:
            return match.group(1)
    return None


def _read_go_module(path: Path) -> str | None:
    """Return the trailing segment of ``module …`` from a go.mod, ignoring /vN."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("module "):
            continue
        module = stripped[len("module "):].strip().strip('"')
        parts = [p for p in module.split("/") if p]
        if (
            len(parts) >= 2
            and parts[-1].startswith("v")
            and parts[-1][1:].isdigit()
        ):
            parts = parts[:-1]
        return parts[-1] if parts else None
    return None


def _read_cargo(path: Path) -> tuple[str | None, str] | None:
    """Read a Cargo.toml. Returns (name, version_key) or None when there's
    nothing to bump (e.g. a workspace-only file with no shared version, or
    a member crate that inherits via ``version.workspace = true``).
    """
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    workspace = doc.get("workspace")
    if isinstance(workspace, dict):
        wpkg = workspace.get("package")
        if isinstance(wpkg, dict) and "version" in wpkg:
            name: str | None = None
            pkg = doc.get("package")
            if isinstance(pkg, dict):
                pkg_name = pkg.get("name")
                if pkg_name:
                    name = str(pkg_name)
            return (name, "workspace.package.version")

    pkg = doc.get("package")
    if not isinstance(pkg, dict):
        return None
    pkg_version = pkg.get("version")
    if pkg_version is None or isinstance(pkg_version, dict):
        # missing or inheriting from workspace
        return None
    pkg_name = pkg.get("name")
    if not pkg_name:
        return None
    return (str(pkg_name), "package.version")


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

    for cargo_path in _find_manifests(repo, "Cargo.toml"):
        info = _read_cargo(cargo_path)
        if info is None:
            continue
        raw_name, version_key = info
        if not raw_name:
            continue
        rel_dir = cargo_path.parent.relative_to(repo)
        comp_name = _unique(raw_name, set(components), suffix="crate")
        if rel_dir == Path("."):
            paths = ["src/**", "Cargo.toml"]
            if (repo / "Cargo.lock").is_file():
                paths.append("Cargo.lock")
            if (repo / "tests").is_dir():
                paths.append("tests/**")
            if (repo / "Dockerfile").is_file():
                paths.append("Dockerfile")
            changelog = Path("CHANGELOG.md")
        else:
            paths = [f"{rel_dir.as_posix()}/**"]
            changelog = Path(f"{rel_dir.as_posix()}/CHANGELOG.md")
        components[comp_name] = Component(
            paths=paths,
            bump_files=[FileKey(file=cargo_path.relative_to(repo), key=version_key)],
            changelog=changelog,
        )

    properties_path = repo / "gradle.properties"
    if properties_path.is_file():
        version = _read_gradle_property(properties_path, "version")
        if version is not None:
            name = _read_gradle_root_name(repo) or repo.name
            comp_name = _unique(name, set(components), suffix="gradle")
            paths = ["gradle.properties"]
            if (repo / "src").is_dir():
                paths.insert(0, "src/**")
            for fn in (
                "build.gradle",
                "build.gradle.kts",
                "settings.gradle",
                "settings.gradle.kts",
            ):
                if (repo / fn).is_file():
                    paths.append(fn)
            if (repo / "Dockerfile").is_file():
                paths.append("Dockerfile")
            components[comp_name] = Component(
                paths=paths,
                bump_files=[
                    FileKey(file=Path("gradle.properties"), key="version")
                ],
                changelog=Path("CHANGELOG.md"),
            )

    for gomod_path in _find_manifests(repo, "go.mod"):
        name = _read_go_module(gomod_path)
        if not name:
            continue
        rel_dir = gomod_path.parent.relative_to(repo)
        comp_name = _unique(name, set(components), suffix="go")
        if rel_dir == Path("."):
            paths = ["**/*.go", "go.mod"]
            if (repo / "go.sum").is_file():
                paths.append("go.sum")
            if (repo / "Dockerfile").is_file():
                paths.append("Dockerfile")
            changelog = Path("CHANGELOG.md")
        else:
            paths = [f"{rel_dir.as_posix()}/**"]
            changelog = Path(f"{rel_dir.as_posix()}/CHANGELOG.md")
        components[comp_name] = Component(
            paths=paths,
            bump_files=[],  # Go is tag-driven
            changelog=changelog,
        )

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

    _detect_node(repo, components, python_name=python_name)

    return components


def _detect_node(
    repo: Path,
    components: dict[str, Component],
    *,
    python_name: str | None,
) -> None:
    """Add Node.js components, expanding workspaces when declared."""
    package_json = repo / "package.json"
    pnpm_workspace = repo / "pnpm-workspace.yaml"
    workspace_globs = _read_workspace_globs(package_json, pnpm_workspace)

    if workspace_globs:
        for pattern in workspace_globs:
            for member in sorted(repo.glob(f"{pattern}/package.json")):
                if any(
                    part in _NOISE_DIRS for part in member.relative_to(repo).parts
                ):
                    continue
                name = _read_package_json_name(member)
                version = _read_package_json_version(member)
                if not name or version is None:
                    continue
                comp_name = _unique(name, set(components), suffix="js")
                rel_dir = member.parent.relative_to(repo).as_posix()
                components[comp_name] = Component(
                    paths=[f"{rel_dir}/**"],
                    bump_files=[
                        FileKey(file=member.relative_to(repo), key="version")
                    ],
                    changelog=Path(f"{rel_dir}/CHANGELOG.md"),
                )
        return

    if package_json.is_file():
        name = _read_package_json_name(package_json)
        if name:
            comp_name = _unique(name, set(components), suffix="js")
            paths = ["package.json"]
            if python_name is None and (repo / "src").is_dir():
                paths.insert(0, "src/**")
            components[comp_name] = Component(
                paths=paths,
                bump_files=[FileKey(file=Path("package.json"), key="version")],
                changelog=Path("CHANGELOG.md") if python_name is None else None,
            )


def _read_package_json_version(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data.get("version") if isinstance(data, dict) else None


def _read_workspace_globs(
    package_json: Path, pnpm_workspace: Path
) -> list[str]:
    """Return workspace member globs from npm/yarn (package.json) or pnpm.

    Recognised shapes:

    * ``"workspaces": ["packages/*"]`` (npm, yarn classic)
    * ``"workspaces": {"packages": ["packages/*"]}`` (yarn berry)
    * ``pnpm-workspace.yaml`` with ``packages: [...]``
    """
    globs: list[str] = []
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if isinstance(data, dict):
            workspaces = data.get("workspaces")
            if isinstance(workspaces, list):
                globs = [str(g) for g in workspaces if isinstance(g, str)]
            elif isinstance(workspaces, dict):
                packages = workspaces.get("packages")
                if isinstance(packages, list):
                    globs = [str(g) for g in packages if isinstance(g, str)]
    if not globs and pnpm_workspace.is_file():
        try:
            data = YAML(typ="safe").load(
                pnpm_workspace.read_text(encoding="utf-8")
            ) or {}
        except Exception:
            data = {}
        packages = data.get("packages") if isinstance(data, dict) else None
        if isinstance(packages, list):
            globs = [str(g) for g in packages if isinstance(g, str)]
    return globs


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
