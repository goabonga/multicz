# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Debian source-package changelog parsing and rendering.

A ``debian/changelog`` is a concatenation of *stanzas* in a strict
five-line shape::

    package (version) distribution; urgency=medium

      * Bullet describing change one.
      * Bullet describing change two.

     -- Maintainer Name <maintainer@example.com>  Mon, 15 Jan 2024 12:34:56 +0100

Multiple stanzas are stacked newest-first. ``multicz`` reads the
*topmost* stanza for the canonical version and prepends a freshly
rendered stanza on every bump — old stanzas are never rewritten,
matching the contract of ``dch(1)``.

Debian version strings can include an ``epoch:``, an upstream component,
and a ``-debian_revision`` suffix (e.g. ``2:1.2.3-5``). multicz works
with the upstream component for its semver math and re-attaches the
configured Debian revision when writing a new stanza.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime

from .commits import Commit

_HEADER_RE = re.compile(
    r"^(?P<package>[a-z0-9][a-z0-9+\-.]*)\s+"
    r"\((?P<version>[^)]+)\)\s+"
    r"(?P<distribution>[^;\s]+);"
)
_TRAILER_PREFIX = " -- "


@dataclass(frozen=True)
class DebianStanza:
    package: str
    version: str
    distribution: str
    body: str
    trailer: str


def parse_top_stanza(text: str) -> DebianStanza | None:
    """Return the topmost stanza of a Debian changelog, or ``None``."""
    if not text or not text.strip():
        return None
    lines = text.splitlines()
    header_match = _HEADER_RE.match(lines[0])
    if not header_match:
        return None

    body_lines: list[str] = []
    trailer = ""
    for line in lines[1:]:
        if line.startswith(_TRAILER_PREFIX):
            trailer = line
            break
        body_lines.append(line)

    return DebianStanza(
        package=header_match.group("package"),
        version=header_match.group("version"),
        distribution=header_match.group("distribution"),
        body="\n".join(body_lines).strip("\n"),
        trailer=trailer,
    )


def parse_top_version(text: str) -> str | None:
    stanza = parse_top_stanza(text)
    return stanza.version if stanza else None


def upstream_version(debian_version: str) -> str:
    """Return the upstream component of ``debian_version``.

    >>> upstream_version("1.2.3")
    '1.2.3'
    >>> upstream_version("1.2.3-1")
    '1.2.3'
    >>> upstream_version("2:1.2.3-5")
    '1.2.3'
    """
    if ":" in debian_version:
        debian_version = debian_version.split(":", 1)[1]
    if "-" in debian_version:
        debian_version = debian_version.rsplit("-", 1)[0]
    return debian_version


_SEMVER_PRE_RE = re.compile(r"^(?P<base>\d+(?:\.\d+){0,2})-(?P<label>[A-Za-z]+)\.(?P<num>\d+)$")


_DEBIAN_PRE_RE = re.compile(
    r"^(?P<base>\d+(?:\.\d+){0,2})~(?P<label>[A-Za-z]+)(?P<num>\d+)$"
)


def to_debian_pre(upstream: str) -> str:
    """Convert a semver-style pre-release suffix to Debian's tilde form.

    Debian sorts ``~`` before nothing, so ``1.3.0~rc1 < 1.3.0`` in dpkg
    ordering — exactly what you want for a release candidate. semver's
    ``1.3.0-rc.1`` would sort *after* ``1.3.0`` in dpkg, which is wrong.

    >>> to_debian_pre("1.3.0")
    '1.3.0'
    >>> to_debian_pre("1.3.0-rc.1")
    '1.3.0~rc1'
    >>> to_debian_pre("2.0.0-alpha.4")
    '2.0.0~alpha4'
    """
    match = _SEMVER_PRE_RE.match(upstream)
    if not match:
        return upstream
    return f"{match.group('base')}~{match.group('label')}{match.group('num')}"


def from_debian_pre(debian_upstream: str) -> str:
    """Inverse of :func:`to_debian_pre`. Converts ``1.3.0~rc1`` back to
    ``1.3.0-rc.1`` so :class:`packaging.version.Version` can parse it.

    >>> from_debian_pre("1.3.0")
    '1.3.0'
    >>> from_debian_pre("1.3.0~rc1")
    '1.3.0-rc.1'
    """
    match = _DEBIAN_PRE_RE.match(debian_upstream)
    if not match:
        return debian_upstream
    return f"{match.group('base')}-{match.group('label')}.{match.group('num')}"


def format_debian_version(
    upstream: str,
    *,
    debian_revision: int = 1,
    epoch: int | None = None,
) -> str:
    """Compose a full Debian version from its parts.

    Pre-release suffixes in semver form (``-rc.1``) are converted to
    Debian's ``~rc1`` form so that ``apt`` orders RCs *before* the
    final release.

    >>> format_debian_version("1.2.3")
    '1.2.3-1'
    >>> format_debian_version("1.2.3", debian_revision=3)
    '1.2.3-3'
    >>> format_debian_version("1.2.3", epoch=2)
    '2:1.2.3-1'
    >>> format_debian_version("1.3.0-rc.1")
    '1.3.0~rc1-1'
    """
    parts: list[str] = []
    if epoch is not None:
        parts.append(f"{epoch}:")
    parts.append(to_debian_pre(upstream))
    parts.append(f"-{debian_revision}")
    return "".join(parts)


def _capitalize(subject: str) -> str:
    if not subject:
        return subject
    return subject[0].upper() + subject[1:]


def _bullet(commit: Commit) -> str:
    scope = f"({commit.scope})" if commit.scope else ""
    bang = "!" if commit.breaking else ""
    return f"  * {commit.type}{scope}{bang}: {_capitalize(commit.subject)}"


def render_stanza(
    *,
    package: str,
    version: str,
    distribution: str = "UNRELEASED",
    urgency: str = "medium",
    commits: Iterable[Commit] = (),
    maintainer: str = "Unknown <unknown@example.com>",
    when: datetime | None = None,
) -> str:
    """Render a single Debian changelog stanza, ending with a trailing
    newline so concatenated stanzas are separated by a blank line.
    """
    when = when or datetime.now(tz=UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)

    relevant = [c for c in commits if c.is_conventional]
    body = (
        "\n".join(_bullet(c) for c in relevant)
        if relevant
        else "  * No notable changes."
    )

    date = format_datetime(when)
    return (
        f"{package} ({version}) {distribution}; urgency={urgency}\n"
        f"\n"
        f"{body}\n"
        f"\n"
        f" -- {maintainer}  {date}\n"
    )


def drop_prerelease_stanzas(text: str, base_version: str) -> str:
    """Remove stanzas whose version matches ``<base_version>~<pre><n>``.

    Used by the ``promote`` finalize strategy: once ``mypkg (1.3.0-1)`` has
    been written, the now-superseded ``mypkg (1.3.0~rc1-1)``,
    ``mypkg (1.3.0~rc2-1)``, … stanzas are removed.

    Stanzas are split on the trailer line (``" -- "``) to keep parsing
    robust against irregular blank-line spacing.
    """
    pre_re = re.compile(
        r"^[a-z0-9][a-z0-9+\-.]*\s+\(" + re.escape(base_version) + r"~[A-Za-z]+\d+(-\d+)?\)\s+"
    )
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines(keepends=True):
        current.append(line)
        if line.startswith(_TRAILER_PREFIX):
            chunks.append("".join(current))
            current = []
    if current:
        chunks.append("".join(current))

    kept: list[str] = []
    for chunk in chunks:
        first = chunk.lstrip("\n")
        if not first or pre_re.match(first):
            continue
        kept.append(chunk)
    if not kept:
        return ""
    out = "".join(kept)
    if not out.endswith("\n"):
        out += "\n"
    return out


def prepend_stanza(existing: str, stanza: str) -> str:
    """Insert ``stanza`` at the top of an existing changelog.

    Stanzas are separated from each other by a blank line. Empty input
    returns the stanza verbatim.
    """
    if not stanza.endswith("\n"):
        stanza += "\n"
    if not existing.strip():
        return stanza
    if not existing.endswith("\n"):
        existing += "\n"
    return f"{stanza}\n{existing}"
