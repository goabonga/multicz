"""Configuration schema for multicz.

The config lives in ``multicz.toml`` at the repo root. It declares one or more
*components*, each owning a set of glob paths, version files to bump, and
optional mirrors that propagate the component's version into other files
(typically ``Chart.yaml:appVersion``).

A modification to a file owned by component A bumps A. If A has a mirror that
writes into a file owned by component B, B cascades a patch bump (option A:
strict Helm chart immutability).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_FILENAME = "multicz.toml"

# Alternate hosts for the config, in precedence order. The dedicated
# multicz.toml always wins when present.
_ALT_HOSTS: tuple[str, ...] = ("pyproject.toml", "package.json")


class FileKey(BaseModel):
    """A pointer to a value inside a structured file.

    ``key`` is a dotted path (e.g. ``project.version`` or ``image.tag``).
    ``None`` means the whole file is a single version literal.
    """

    model_config = ConfigDict(extra="forbid")

    file: Path
    key: str | None = None


class DebianSettings(BaseModel):
    """Per-component settings for ``format = "debian"`` packaging.

    The component's version is read from the topmost stanza of
    ``changelog`` (default ``debian/changelog``) and a new stanza is
    *prepended* on every bump — older stanzas are never rewritten.
    """

    model_config = ConfigDict(extra="forbid")

    changelog: Path = Path("debian/changelog")
    distribution: str = "UNRELEASED"
    urgency: str = "medium"
    maintainer: str | None = None  # falls back to debian/control then git config
    debian_revision: int = 1
    epoch: int | None = None


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(min_length=1)
    exclude_paths: list[str] = Field(default_factory=list)
    bump_files: list[FileKey] = Field(default_factory=list)
    mirrors: list[FileKey] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    changelog: Path | None = None
    format: Literal["default", "debian"] = "default"
    debian: DebianSettings | None = None

    @field_validator("paths", "exclude_paths")
    @classmethod
    def _strip_globs(cls, value: list[str]) -> list[str]:
        return [v.strip() for v in value if v.strip()]

    @model_validator(mode="after")
    def _validate_format(self) -> Component:
        if self.format == "debian":
            if self.debian is None:
                self.debian = DebianSettings()
            if self.bump_files:
                raise ValueError(
                    "components with format='debian' read the version from "
                    "debian/changelog; remove bump_files."
                )
            if self.mirrors:
                raise ValueError(
                    "mirrors are not supported on format='debian' components."
                )
            if self.changelog is not None:
                raise ValueError(
                    "use [components.<name>.debian].changelog instead of the "
                    "top-level 'changelog' field for debian-format components."
                )
        elif self.debian is not None:
            raise ValueError(
                "the [components.<name>.debian] table is only valid when "
                "format = 'debian'."
            )
        return self


class ChangelogSection(BaseModel):
    """A bucket in the rendered CHANGELOG.md.

    Commits whose conventional-commit type matches any of ``types``
    (case-insensitive) land in this section. Sections are emitted in their
    declaration order, after the implicit Breaking changes block. Commits
    whose type matches no section are silently dropped unless
    ``ProjectSettings.other_section_title`` is set.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    types: list[str] = Field(min_length=1)


def _default_changelog_sections() -> list[ChangelogSection]:
    return [
        ChangelogSection(title="Features", types=["feat"]),
        ChangelogSection(title="Fixes", types=["fix"]),
        ChangelogSection(title="Performance", types=["perf"]),
    ]


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit_convention: Literal["conventional"] = "conventional"
    tag_format: str = "{component}-v{version}"
    initial_version: str = "0.1.0"
    release_commit_pattern: str = r"^chore\(release\)"
    changelog_sections: list[ChangelogSection] = Field(
        default_factory=_default_changelog_sections
    )
    breaking_section_title: str = "Breaking changes"
    other_section_title: str = ""
    finalize_strategy: Literal["consolidate", "promote", "annotate"] = "consolidate"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectSettings = Field(default_factory=ProjectSettings)
    components: dict[str, Component]

    @model_validator(mode="before")
    @classmethod
    def _accept_components_array(cls, data: Any) -> Any:
        """Normalise the array-of-tables form ``[[components]]`` into the
        dict-of-tables form internally used by the rest of the code.

        Both these snippets parse to the same :class:`Config`::

            [components.api]
            paths = ["src/**"]

            [[components]]
            name = "api"
            paths = ["src/**"]
        """
        if not isinstance(data, dict):
            return data
        raw = data.get("components")
        if not isinstance(raw, list):
            return data

        converted: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ValueError(
                    f"components[{index}] must be a table, got "
                    f"{type(item).__name__}"
                )
            name = item.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(
                    f"components[{index}] is missing a string 'name' field"
                )
            if name in converted:
                raise ValueError(f"duplicate component name: {name!r}")
            converted[name] = {k: v for k, v in item.items() if k != "name"}

        return {**data, "components": converted}

    @field_validator("components")
    @classmethod
    def _non_empty(cls, value: dict[str, Component]) -> dict[str, Component]:
        if not value:
            raise ValueError("at least one component must be declared")
        return value

    def validate_references(self) -> None:
        """Ensure ``triggers`` only references known components."""
        names = set(self.components)
        for name, comp in self.components.items():
            unknown = set(comp.triggers) - names
            if unknown:
                raise ValueError(
                    f"component {name!r} triggers unknown component(s): "
                    f"{', '.join(sorted(unknown))}"
                )


def _extract_section(path: Path) -> dict[str, Any] | None:
    """Return the multicz config dict embedded in ``path``, or ``None``.

    For ``pyproject.toml`` the section is ``[tool.multicz]``.
    For ``package.json`` the section is the top-level ``"multicz"`` key.
    For ``multicz.toml`` the whole document is the config.
    """
    name = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    if name == CONFIG_FILENAME:
        try:
            return tomlkit.parse(text).unwrap()
        except Exception:
            return None
    if name == "pyproject.toml":
        try:
            doc = tomlkit.parse(text).unwrap()
        except Exception:
            return None
        tool = doc.get("tool")
        if isinstance(tool, dict):
            section = tool.get("multicz")
            if isinstance(section, dict):
                return section
        return None
    if name == "package.json":
        try:
            data = json.loads(text)
        except Exception:
            return None
        section = data.get("multicz") if isinstance(data, dict) else None
        return section if isinstance(section, dict) else None
    return None


def load_config(path: Path) -> Config:
    """Load and validate a multicz config from ``path``.

    Accepts ``multicz.toml`` (whole-file), ``pyproject.toml``
    (``[tool.multicz]``), or ``package.json`` (``"multicz"`` key).
    """
    raw = _extract_section(path)
    if raw is None:
        raise FileNotFoundError(
            f"no multicz config found in {path}"
        )
    config = Config.model_validate(raw)
    config.validate_references()
    return config


def find_config(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: cwd) looking for a multicz config.

    At each directory level, the search order is:

    1. ``multicz.toml`` (always wins when present),
    2. ``pyproject.toml`` with a ``[tool.multicz]`` table,
    3. ``package.json`` with a top-level ``"multicz"`` key.
    """
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        canonical = directory / CONFIG_FILENAME
        if canonical.is_file():
            return canonical
        for filename in _ALT_HOSTS:
            candidate = directory / filename
            if candidate.is_file() and _extract_section(candidate) is not None:
                return candidate
    raise FileNotFoundError(
        "no multicz config found (looked for multicz.toml, "
        "pyproject.toml [tool.multicz], or package.json \"multicz\" key) "
        f"in {here} or any parent directory"
    )
