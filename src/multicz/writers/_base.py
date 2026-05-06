# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Common types for the writer Strategy + Registry.

A *writer* is a sink declared inside ``[[components.<name>.writers]]``.
On every bump multicz calls each writer's :meth:`WriterImpl.write` method
with a :class:`WriteContext`; the writer renders its sink (e.g. prepend
a Debian changelog stanza) and returns the files it touched so the bump
pipeline can fold them into the release commit.

A writer may also act as the *version source of truth* when the
component declares no ``bump_files``: :meth:`WriterImpl.read_version`
returns the version it knows about (e.g. parsed from the topmost stanza
of ``debian/changelog``) or ``None`` if it isn't a source kind.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..commits import Commit
    from ..config import Component, Config, Writer
    from ..planner import PlannedBump
    from ..validation._base import Finding


@dataclass(frozen=True)
class WriteContext:
    """Inputs handed to every :meth:`WriterImpl.write` invocation.

    Carries everything a writer might need without forcing it back to
    rebuild the commit list / matcher / maintainer string itself. The
    bump pipeline assembles this once per planned component.
    """

    repo: Path
    component_name: str
    component: Component
    writer: Writer
    planned: PlannedBump
    new_version: str
    config: Config
    relevant_commits: Sequence[Commit]
    is_finalize: bool


class WriterImpl(Protocol):
    """Plugin contract for one writer kind.

    The Pydantic model lives next to the schema (``config/models.py``);
    the impl lives here. Both are linked by the ``type`` discriminator.
    """

    name: str  # matches the writer model's ``type`` discriminator

    def matches(self, writer: Writer) -> bool:
        """Return ``True`` when ``writer`` is the kind this impl handles."""

    def read_version(self, writer: Writer, repo: Path) -> str | None:
        """Read the upstream version this writer claims, or ``None`` if
        the writer isn't a version source for this kind."""

    def write(self, ctx: WriteContext) -> list[Path]:
        """Render and write the sink. Return absolute paths the writer
        touched (so the bump pipeline can stage them)."""

    def validate(self, writer: Writer, repo: Path) -> Iterator[Finding]:
        """Validation findings for ``writer`` against the on-disk repo
        state. May yield zero or more :class:`Finding` items."""
