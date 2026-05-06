# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Render and write per-component sinks at bump time.

Each writer kind (e.g. ``debian-changelog``) is a small impl class
implementing :class:`WriterImpl` (see :mod:`._base`). The registry
below dispatches a :class:`config.Writer` instance to the matching
impl.

Adding a new writer kind:

1. add a Pydantic model in ``config/models.py`` and append it to the
   :data:`Writer` discriminated union;
2. add a ``MyKindImpl`` here and append it to :data:`WRITERS`;
3. existing call-sites (planner, bump, validation) need no changes.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Writer
from ._base import WriteContext, WriterImpl
from .debian_changelog import DebianChangelogImpl

WRITERS: list[WriterImpl] = [
    DebianChangelogImpl(),
]

__all__ = [
    "WRITERS",
    "DebianChangelogImpl",
    "WriteContext",
    "WriterImpl",
    "impl_for",
    "read_version_from_writers",
]


def impl_for(writer: Writer) -> WriterImpl:
    """Return the impl handling ``writer``. Raises if no impl matches."""
    for impl in WRITERS:
        if impl.matches(writer):
            return impl
    raise LookupError(
        f"no WriterImpl claimed writer of type {type(writer).__name__!r}; "
        f"register one in multicz.writers.WRITERS."
    )


def read_version_from_writers(writers: list[Writer], repo: Path) -> str | None:
    """First-match wins: ask each writer if it can claim the version
    source role, return the first non-``None`` answer."""
    for writer in writers:
        impl = impl_for(writer)
        version = impl.read_version(writer, repo)
        if version is not None:
            return version
    return None
