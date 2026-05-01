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

from .config import Component, DebianSettings, FileKey
from .debian import parse_top_stanza

_GRADLE_NAME_RE = re.compile(
    r"rootProject\.name\s*=\s*['\"]([^'\"]+)['\"]"
)


def _read_pyproject_info(path: Path) -> tuple[str, str] | None:
    """Return ``(name, version_key)`` for a Python project, or ``None``.

    Handles both PEP 621 (``[project]``, used by uv/hatch/setuptools-pep621
    and modern Poetry) and legacy Poetry (``[tool.poetry]``). Files that
    declare neither are typically uv workspace orchestrators and are
    skipped (returning ``None``).
    """
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    project = doc.get("project")
    if isinstance(project, dict):
        name = project.get("name")
        if name and "version" in project:
            return (str(name), "project.version")

    tool = doc.get("tool")
    if isinstance(tool, dict):
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            name = poetry.get("name")
            version = poetry.get("version")
            if name and version is not None:
                return (str(name), "tool.poetry.version")

    return None


def _read_uv_workspace(path: Path) -> tuple[list[str], list[str]]:
    """Return ``(members_globs, exclude_globs)`` from ``[tool.uv.workspace]``."""
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return [], []
    tool = doc.get("tool")
    if not isinstance(tool, dict):
        return [], []
    uv = tool.get("uv")
    if not isinstance(uv, dict):
        return [], []
    workspace = uv.get("workspace")
    if not isinstance(workspace, dict):
        return [], []

    def _list(value) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value if isinstance(v, str)]
        return []

    return _list(workspace.get("members")), _list(workspace.get("exclude"))


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


def _read_cargo_excludes(repo: Path) -> set[Path]:
    """Resolve ``[workspace].exclude`` paths from a root Cargo.toml.

    Each entry is a directory path (not a glob). The contained
    ``Cargo.toml`` is what we want to skip during discovery.
    """
    root = repo / "Cargo.toml"
    if not root.is_file():
        return set()
    try:
        doc = tomlkit.parse(root.read_text(encoding="utf-8"))
    except Exception:
        return set()
    workspace = doc.get("workspace")
    if not isinstance(workspace, dict):
        return set()
    excludes = workspace.get("exclude")
    if not isinstance(excludes, list):
        return set()
    out: set[Path] = set()
    for entry in excludes:
        if not isinstance(entry, str):
            continue
        candidate = (repo / entry / "Cargo.toml")
        if candidate.is_file():
            out.add(candidate.resolve())
    return out


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
    python_names: list[str] = []
    python_raw_names: dict[str, str] = {}

    # Collect every pyproject.toml (uv/hatch/setuptools/Poetry) and apply the
    # uv workspace exclude list when the root declares one.
    pyprojects = _find_manifests(repo, "pyproject.toml")
    excluded: set[Path] = set()
    root_pyproject = repo / "pyproject.toml"
    if root_pyproject.is_file():
        _, ws_excludes = _read_uv_workspace(root_pyproject)
        for pattern in ws_excludes:
            for path in repo.glob(f"{pattern}/pyproject.toml"):
                excluded.add(path.resolve())

    for path in pyprojects:
        if path.resolve() in excluded:
            continue
        info = _read_pyproject_info(path)
        if info is None:
            continue  # uv workspace orchestrator with no [project], skip
        raw_name, version_key = info
        rel_dir = path.parent.relative_to(repo)
        comp_name = _unique(raw_name, set(components), suffix="py")
        if rel_dir == Path("."):
            paths = ["pyproject.toml"]
            if (repo / "src").is_dir():
                paths.insert(0, "src/**")
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
            bump_files=[FileKey(file=path.relative_to(repo), key=version_key)],
            changelog=changelog,
        )
        python_names.append(comp_name)
        python_raw_names[comp_name] = raw_name

    cargo_excluded = _read_cargo_excludes(repo)
    for cargo_path in _find_manifests(repo, "Cargo.toml"):
        if cargo_path.resolve() in cargo_excluded:
            continue
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

    if python_names and chart_names:
        # Single python + single chart: unambiguous, always pair.
        # Otherwise: match by name, so a 'worker' chart next to an 'api' python
        # project stays independent and a multi-python repo wires each python
        # to its same-named chart only.
        if len(python_names) == 1 and len(chart_names) == 1:
            py = components[python_names[0]]
            chart_yaml_path = components[chart_names[0]].bump_files[0].file
            py.mirrors.append(FileKey(file=chart_yaml_path, key="appVersion"))
        else:
            for py_name in python_names:
                py = components[py_name]
                py_raw = python_raw_names[py_name]
                for chart_comp_name in chart_names:
                    if chart_raw_names[chart_comp_name] == py_raw:
                        chart_yaml_path = components[chart_comp_name].bump_files[0].file
                        py.mirrors.append(
                            FileKey(file=chart_yaml_path, key="appVersion")
                        )

    _detect_node(repo, components, python_taken=bool(python_names))
    _detect_debian(repo, components)

    return components


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
    comp_name = _unique(raw_name, set(components), suffix="deb")
    paths = ["debian/**"]
    if (repo / "src").is_dir():
        paths.append("src/**")
    components[comp_name] = Component(
        paths=paths,
        format="debian",
        debian=DebianSettings(),
    )


def _detect_node(
    repo: Path,
    components: dict[str, Component],
    *,
    python_taken: bool,
) -> None:
    """Add Node.js components, expanding workspaces when declared.

    When the repo declares a workspace (npm/yarn ``"workspaces"`` array,
    yarn-berry ``"workspaces.packages"``, or ``pnpm-workspace.yaml``), only
    the listed members are added — the user has been explicit about what
    is and isn't part of the workspace.

    When no workspace is declared, every ``package.json`` outside noise dirs
    is added as its own component. That covers the common FastAPI + React
    layout where the SPA sits in ``frontend/`` next to a root pyproject.
    """
    root_pkg = repo / "package.json"
    pnpm_ws = repo / "pnpm-workspace.yaml"
    workspace_globs = _read_workspace_globs(root_pkg, pnpm_ws)

    # npm/yarn/pnpm support '!pattern' to exclude members from a workspace.
    include_globs = [g for g in workspace_globs if not g.startswith("!")]
    exclude_globs = [g[1:] for g in workspace_globs if g.startswith("!")]

    candidates: list[Path] = []
    if include_globs:
        excluded_paths: set[Path] = set()
        for pattern in exclude_globs:
            for member in repo.glob(f"{pattern}/package.json"):
                excluded_paths.add(member.resolve())
        for pattern in include_globs:
            for member in sorted(repo.glob(f"{pattern}/package.json")):
                if any(
                    part in _NOISE_DIRS for part in member.relative_to(repo).parts
                ):
                    continue
                if member.resolve() in excluded_paths:
                    continue
                candidates.append(member)
    elif workspace_globs:
        # globs were declared but they're all '!exclusions' with no includes —
        # nothing to add.
        return
    else:
        candidates = _find_manifests(repo, "package.json")

    for path in candidates:
        name = _read_package_json_name(path)
        version = _read_package_json_version(path)
        if not name or version is None:
            continue
        comp_name = _unique(name, set(components), suffix="js")
        rel_dir = path.parent.relative_to(repo)
        if rel_dir == Path("."):
            paths = ["package.json"]
            if not python_taken and (repo / "src").is_dir():
                paths.insert(0, "src/**")
            changelog: Path | None = (
                Path("CHANGELOG.md") if not python_taken else None
            )
        else:
            paths = [f"{rel_dir.as_posix()}/**"]
            changelog = Path(f"{rel_dir.as_posix()}/CHANGELOG.md")
        components[comp_name] = Component(
            paths=paths,
            bump_files=[FileKey(file=path.relative_to(repo), key="version")],
            changelog=changelog,
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
        if comp.format != "default":
            section["format"] = comp.format
        if comp.debian is not None:
            debian_table = tomlkit.table()
            debian_table["changelog"] = str(comp.debian.changelog)
            debian_table["distribution"] = comp.debian.distribution
            debian_table["urgency"] = comp.debian.urgency
            debian_table["debian_revision"] = comp.debian.debian_revision
            if comp.debian.maintainer is not None:
                debian_table["maintainer"] = comp.debian.maintainer
            if comp.debian.epoch is not None:
                debian_table["epoch"] = comp.debian.epoch
            section["debian"] = debian_table
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
