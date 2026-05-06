# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Pydantic schema for the multicz configuration.

This module owns the *shape* of the config (Component, ProjectSettings,
Config, ...). Source-loading (TOML / JSON, search-up-the-tree) lives in
``sources.py``.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..commits import DEFAULT_BUMP_RULES, BumpRule

# Component names land in git tag names, file paths (CHANGELOG.md location),
# JSON output, release-notes headings, and CLI arguments
# (`--force NAME:KIND`). Restrict them to a safe alphabet so none of those
# downstream uses can break unexpectedly.
COMPONENT_NAME_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9_.-]*[a-zA-Z0-9])?$")
COMPONENT_NAME_MAX_LEN = 64


class FileKey(BaseModel):
    """A pointer to a value inside a structured file.

    ``key`` is a dotted path (e.g. ``project.version`` or ``image.tag``).
    ``None`` means the whole file is a single version literal.
    """

    model_config = ConfigDict(extra="forbid")

    file: Path
    key: str | None = None


class Mirror(FileKey):
    """A mirror target with optional changelog customization.

    Inherits ``file`` / ``key`` from :class:`FileKey`. Adds two optional
    fields that customize how the resulting cascade line is rendered in
    the *downstream* component's CHANGELOG when this mirror triggers a
    bump there:

    * ``changelog_section`` - routes the cascade line to a specific
      section. Can be the title of an existing section
      (``Features``, ``Fixes``, ``Dependencies``, ...) or any custom
      name. When unset, the line falls under the project-level
      ``cascade_section_title`` (default: ``Dependencies``).
    * ``changelog_format`` - overrides the default cascade phrase for
      this specific mirror. The template accepts ``{upstream}`` and
      ``{upstream_version}`` placeholders. When unset, the project-level
      ``cascade_changelog_format`` applies.
    """

    changelog_section: str | None = None
    changelog_format: str | None = None


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


class DebianChangelogWriter(BaseModel):
    """A ``debian/changelog`` sink: a fresh stanza is prepended on every
    bump, older stanzas are preserved verbatim.

    Declared inside a component's ``[[writers]]`` array. When the
    component has no ``bump_files``, this writer also acts as the
    *version source of truth* — multicz reads the upstream version from
    the topmost stanza. With ``bump_files`` declared, the writer is a
    pure sink and the version source is the primary bump_file (typical
    "Python wheel + .deb" or "Cargo crate + .deb" setup).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["debian-changelog"]
    file: Path = Path("debian/changelog")
    distribution: str = "UNRELEASED"
    urgency: str = "medium"
    maintainer: str | None = None  # falls back to debian/control then git config
    debian_revision: int = 1
    epoch: int | None = None


# Discriminated union of all writer types. Add new writer schemas here
# and a matching impl in ``multicz.writers`` (Strategy + Registry).
Writer = Annotated[
    DebianChangelogWriter,
    Field(discriminator="type"),
]


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(min_length=1)
    exclude_paths: list[str] = Field(default_factory=list)
    bump_files: list[FileKey] = Field(default_factory=list)
    mirrors: list[Mirror] = Field(default_factory=list)
    # depends_on lists upstream components whose bump should cascade into
    # this one.
    depends_on: list[str] = Field(default_factory=list)
    changelog: Path | None = None
    # Sinks that get rewritten on every bump (and may also act as the
    # *version source* when ``bump_files`` is empty - useful for pure
    # Debian source packages with no pyproject/Cargo/package.json).
    # See :data:`Writer` for the supported types.
    writers: list[Writer] = Field(default_factory=list)
    tag_format: str | None = None  # overrides the project-level tag_format
    bump_policy: Literal["as-commit", "scoped"] = "as-commit"
    # Sparse override over ``project.bump_rules`` (component wins per type).
    # Map a conventional-commit type to its bump level: ``major`` /
    # ``minor`` / ``patch`` / ``none`` (= silence the type, including its
    # breaking variants).
    bump_rules: dict[str, BumpRule] = Field(default_factory=dict)
    version_scheme: Literal["semver", "pep440"] = "semver"
    artifacts: list[Artifact] = Field(default_factory=list)
    # Shell commands run after multicz has rewritten this component's
    # bump_files but before it stages them for the release commit. The
    # canonical use-case is regenerating lockfiles that depend on the
    # version multicz just wrote (uv.lock, package-lock.json, Cargo.lock,
    # Chart.lock, …). Each entry is parsed via shlex.split and executed
    # in the repo root. Files modified by these hooks are auto-detected
    # and joined to the release commit.
    post_bump: list[str] = Field(default_factory=list)

    @field_validator("paths", "exclude_paths", "post_bump")
    @classmethod
    def _strip_globs(cls, value: list[str]) -> list[str]:
        return [v.strip() for v in value if v.strip()]

    @field_validator("post_bump")
    @classmethod
    def _validate_post_bump_shellable(cls, value: list[str]) -> list[str]:
        """Surface bad quoting at config-load time (i.e. via
        ``multicz validate``) instead of at bump-run time."""
        for entry in value:
            try:
                shlex.split(entry)
            except ValueError as exc:
                raise ValueError(
                    f"post_bump entry {entry!r} is not a valid shell "
                    f"command: {exc}"
                ) from exc
        return value

    @field_validator("bump_rules")
    @classmethod
    def _lowercase_bump_rule_keys(cls, value: dict[str, BumpRule]) -> dict[str, BumpRule]:
        return {k.lower(): v for k, v in value.items()}

    @model_validator(mode="after")
    def _validate_writers(self) -> Component:
        """Constraints on writer declarations:

        * a ``debian-changelog`` writer requires ``version_scheme = "semver"``
          (the renderer's ``~rc1`` notation depends on the internal canonical
          form);
        * file paths must be unique across writers within the component
          (catches a ``[[writers]]`` table accidentally duplicated).
        """
        seen_files: set[Path] = set()
        for writer in self.writers:
            if writer.file in seen_files:
                raise ValueError(
                    f"duplicate writer file {str(writer.file)!r} on this "
                    "component; each writer must point to a distinct path."
                )
            seen_files.add(writer.file)
            if (
                isinstance(writer, DebianChangelogWriter)
                and self.version_scheme != "semver"
            ):
                raise ValueError(
                    "writer type='debian-changelog' requires "
                    "version_scheme='semver' (the internal canonical form); "
                    "the Debian changelog renderer applies its own '~rc1' "
                    "notation."
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
    # Section + line format for cascade-only bumps (mirror or trigger).
    # Replaces the legacy ``_No notable changes._`` placeholder when the
    # only reason for a release is an upstream component bumping. Set
    # ``cascade_section_title = ""`` to disable and fall back to the
    # placeholder. ``cascade_changelog_format`` accepts ``{upstream}`` and
    # ``{upstream_version}`` placeholders.
    cascade_section_title: str = "Dependencies"
    cascade_changelog_format: str = "Track `{upstream}` `{upstream_version}`"
    finalize_strategy: Literal["consolidate", "promote", "annotate"] = "consolidate"
    overlap_policy: Literal["error", "first-match", "allow", "all"] = "error"
    # Bump level per conventional-commit type. Entries map to ``major`` /
    # ``minor`` / ``patch`` / ``none``. A type set to ``"none"`` is fully
    # silenced (its breaking variants are also dropped). Types absent from
    # the map fall back to: skip when not breaking, major when breaking
    # (Conventional Commits default).
    #
    # User-provided entries are *merged on top of* :data:`DEFAULT_BUMP_RULES`
    # so adding a single rule like ``refactor = "patch"`` doesn't silently
    # lose the conventional bump for ``feat`` / ``fix`` / ``perf`` /
    # ``revert``. To silence a default, set it to ``"none"`` explicitly.
    bump_rules: dict[str, BumpRule] = Field(
        default_factory=lambda: dict(DEFAULT_BUMP_RULES)
    )
    state_file: Path | None = None  # opt-in JSON snapshot, written on bump
    unknown_commit_policy: Literal["ignore", "patch", "error"] = "ignore"
    sign_commits: bool = False  # gpg-sign release commits (git commit -S)
    sign_tags: bool = False     # gpg-sign tags (git tag -s)
    # Whether ``[components.<name>] post_bump`` shell hooks are allowed
    # to run. Defaults to ``"deny"`` because post_bump is the *only*
    # multicz feature that executes arbitrary commands sourced from the
    # config — opting in is an explicit, reviewable change. Set to
    # ``"allow"`` to enable; the CLI flag ``--no-post-bump`` can still
    # disable hooks for a specific run.
    post_bump_policy: Literal["deny", "allow"] = "deny"
    # Cascade kind along ``depends_on`` edges. Defaults to ``"patch"``: a
    # dependent (e.g. a Helm chart) doesn't usually *gain* the upstream's
    # feature - it just needs a fresh build referencing the new version.
    # Set to ``"match-upstream"`` to inherit the upstream's kind verbatim.
    trigger_policy: Literal["match-upstream", "patch"] = "patch"

    @field_validator("bump_rules", mode="before")
    @classmethod
    def _merge_default_bump_rules(cls, value: Any) -> Any:
        """Merge user entries on top of :data:`DEFAULT_BUMP_RULES` so a
        sparse override doesn't silently drop conventional bumps."""
        if not isinstance(value, dict):
            return value
        merged = dict(DEFAULT_BUMP_RULES)
        merged.update({k.lower(): v for k, v in value.items()})
        return merged


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
                    "notes - keep them short."
                )
            if not COMPONENT_NAME_RE.match(name):
                raise ValueError(
                    f"invalid component name {name!r}: must match "
                    f"{COMPONENT_NAME_RE.pattern} - "
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

    def bump_rules_for(self, component: str) -> dict[str, BumpRule]:
        """Effective bump rules for ``component``.

        Project rules merged with the component's sparse override; the
        component-level value wins per type.
        """
        rules = dict(self.project.bump_rules)
        comp = self.components.get(component)
        if comp is not None:
            rules.update(comp.bump_rules)
        return rules

    def ignored_types_for(self, component: str) -> set[str]:
        """Return the lowercased commit types silenced for ``component``.

        Derived from :meth:`bump_rules_for`: any type whose effective
        rule is ``"none"`` is considered ignored. Kept for callers that
        still consume ignored-types semantics directly.
        """
        return {
            t for t, kind in self.bump_rules_for(component).items() if kind == "none"
        }

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
