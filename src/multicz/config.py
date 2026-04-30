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

from pathlib import Path
from typing import Literal

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, field_validator

CONFIG_FILENAME = "multicz.toml"


class FileKey(BaseModel):
    """A pointer to a value inside a structured file.

    ``key`` is a dotted path (e.g. ``project.version`` or ``image.tag``).
    ``None`` means the whole file is a single version literal.
    """

    model_config = ConfigDict(extra="forbid")

    file: Path
    key: str | None = None


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(min_length=1)
    exclude_paths: list[str] = Field(default_factory=list)
    bump_files: list[FileKey] = Field(default_factory=list)
    mirrors: list[FileKey] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)

    @field_validator("paths", "exclude_paths")
    @classmethod
    def _strip_globs(cls, value: list[str]) -> list[str]:
        return [v.strip() for v in value if v.strip()]


class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit_convention: Literal["conventional"] = "conventional"
    tag_format: str = "{component}-v{version}"
    initial_version: str = "0.1.0"
    release_commit_pattern: str = r"^chore\(release\)"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectSettings = Field(default_factory=ProjectSettings)
    components: dict[str, Component]

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


def load_config(path: Path) -> Config:
    """Load and validate a multicz config from ``path``."""
    raw = tomlkit.parse(path.read_text(encoding="utf-8"))
    config = Config.model_validate(raw.unwrap())
    config.validate_references()
    return config


def find_config(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: cwd) looking for ``multicz.toml``."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"{CONFIG_FILENAME} not found in {here} or any parent directory"
    )
