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
import re
from pathlib import Path
from typing import Any, Literal

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_FILENAME = "multicz.toml"

# Component names land in git tag names, file paths (CHANGELOG.md location),
# JSON output, release-notes headings, and CLI arguments
# (`--force NAME:KIND`). Restrict them to a safe alphabet so none of those
# downstream uses can break unexpectedly.
COMPONENT_NAME_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9_.-]*[a-zA-Z0-9])?$")
COMPONENT_NAME_MAX_LEN = 64

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


class Artifact(BaseModel):
    """A build artifact a component produces.

    ``multicz`` does *not* build or push artifacts itself; this declaration
    only surfaces structured information for CI (via ``plan --output json``
    or the ``multicz artifacts`` command).

    ``ref`` is a template string accepting ``{version}`` and ``{component}``
    placeholders. Example::

        [[components.api.artifacts]]
        type = "docker"
        ref  = "ghcr.io/foo/myapp:{version}"

        [[components.api.artifacts]]
        type = "docker"
        ref  = "registry.acme.com/myapp:{version}"
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    ref: str = Field(min_length=1)

    def render(self, *, component: str, version: str) -> dict[str, str]:
        return {
            "type": self.type,
            "ref": self.ref.format(component=component, version=version),
        }


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
    # depends_on lists upstream components whose bump should cascade into
    # this one. ``triggers`` is kept as a parse-time alias for users who
    # already wrote it that way; both names normalise to ``depends_on``.
    depends_on: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)  # alias, post-merged
    changelog: Path | None = None
    format: Literal["default", "debian"] = "default"
    debian: DebianSettings | None = None
    tag_format: str | None = None  # overrides the project-level tag_format
    bump_policy: Literal["as-commit", "scoped"] = "as-commit"
    ignored_types: list[str] = Field(default_factory=list)
    version_scheme: Literal["semver", "pep440"] = "semver"
    artifacts: list[Artifact] = Field(default_factory=list)

    @field_validator("paths", "exclude_paths")
    @classmethod
    def _strip_globs(cls, value: list[str]) -> list[str]:
        return [v.strip() for v in value if v.strip()]

    @model_validator(mode="after")
    def _merge_triggers_alias(self) -> Component:
        """Fold ``triggers`` (legacy name) into ``depends_on`` (canonical).

        Both fields are accepted; the union is what the planner reads.
        After the merge ``triggers`` is left empty so the rest of the
        codebase only needs to look at ``depends_on``.
        """
        if self.triggers:
            merged = list(dict.fromkeys([*self.depends_on, *self.triggers]))
            self.depends_on = merged
            self.triggers = []
        return self

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
            if self.version_scheme != "semver":
                raise ValueError(
                    "format='debian' requires version_scheme='semver' (the "
                    "internal canonical form); the Debian changelog "
                    "stanza renderer applies its own '~rc1' notation."
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
        ChangelogSection(title="Reverts", types=["revert"]),
    ]


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit_convention: Literal["conventional"] = "conventional"
    tag_format: str = "{component}-v{version}"
    initial_version: str = "0.1.0"
    release_commit_pattern: str = r"^chore\(release\)"
    release_commit_message: str = "chore(release): bump {summary}\n\n{body}"
    changelog_sections: list[ChangelogSection] = Field(
        default_factory=_default_changelog_sections
    )
    breaking_section_title: str = "Breaking changes"
    other_section_title: str = ""
    finalize_strategy: Literal["consolidate", "promote", "annotate"] = "consolidate"
    overlap_policy: Literal["error", "first-match", "allow", "all"] = "error"
    ignored_types: list[str] = Field(default_factory=list)
    state_file: Path | None = None  # opt-in JSON snapshot, written on bump
    unknown_commit_policy: Literal["ignore", "patch", "error"] = "ignore"
    sign_commits: bool = False  # gpg-sign release commits (git commit -S)
    sign_tags: bool = False     # gpg-sign tags (git tag -s)
    trigger_policy: Literal["match-upstream", "patch"] = "match-upstream"


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

    @field_validator("components")
    @classmethod
    def _validate_names(cls, value: dict[str, Component]) -> dict[str, Component]:
        for name in value:
            if len(name) > COMPONENT_NAME_MAX_LEN:
                raise ValueError(
                    f"component name {name!r} is too long "
                    f"(max {COMPONENT_NAME_MAX_LEN} chars). Component names "
                    "appear in git tags, file paths, JSON output, and release "
                    "notes — keep them short."
                )
            if not COMPONENT_NAME_RE.match(name):
                raise ValueError(
                    f"invalid component name {name!r}: must match "
                    f"{COMPONENT_NAME_RE.pattern} — "
                    "no slashes, colons, spaces, or path-like characters; "
                    "must start and end with a letter or digit. Component "
                    "names land in git tags, file paths, JSON output, and "
                    "release notes; keeping them simple avoids escaping "
                    "issues downstream."
                )
        return value

    def validate_references(self) -> None:
        """Cross-component validation: triggers and tag-prefix uniqueness."""
        names = set(self.components)
        for name, comp in self.components.items():
            unknown = set(comp.depends_on) - names
            if unknown:
                raise ValueError(
                    f"component {name!r} triggers unknown component(s): "
                    f"{', '.join(sorted(unknown))}"
                )

        # Each component must have a unique tag prefix; otherwise the
        # git glob `git tag --list <prefix>*` returns tags from another
        # component and the planner reads the wrong "current" version.
        seen: dict[str, str] = {}
        for name in self.components:
            prefix = self._render_tag_prefix(name)
            if prefix in seen:
                raise ValueError(
                    f"components {seen[prefix]!r} and {name!r} share the same "
                    f"tag prefix {prefix!r}; tags would collide. Set a unique "
                    f"tag_format on at least one of them."
                )
            seen[prefix] = name

    def ignored_types_for(self, component: str) -> set[str]:
        """Return the lowercased commit types ignored for ``component``.

        Effective set is the union of project and component ignored types.
        """
        comp = self.components.get(component)
        comp_set: set[str] = set()
        if comp is not None:
            comp_set = {t.lower() for t in comp.ignored_types}
        return {t.lower() for t in self.project.ignored_types} | comp_set

    def tag_format_for(self, component: str) -> str:
        """Return the effective tag_format for ``component``.

        Per-component override wins, then the project-level default.
        """
        comp = self.components.get(component)
        if comp is not None and comp.tag_format:
            return comp.tag_format
        return self.project.tag_format

    def _render_tag_prefix(self, component: str) -> str:
        fmt = self.tag_format_for(component)
        rendered = fmt.format(component=component, version="\x00V\x00")
        head, _, _ = rendered.partition("\x00V\x00")
        return head


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
