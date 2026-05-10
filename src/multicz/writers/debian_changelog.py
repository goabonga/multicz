# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``debian-changelog`` writer impl.

Prepends a fresh ``package (version) distribution; urgency=...`` stanza
on every bump. Older stanzas are preserved verbatim, matching the
contract of ``dch(1)``. When the component declares no ``bump_files``,
this writer also acts as the version source of truth - the upstream
version is parsed from the topmost stanza.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

from ..changelog import (
    drop_prerelease_stanzas,
    format_debian_version,
    from_debian_pre,
    parse_top_stanza,
    parse_top_version,
    prepend_stanza,
    render_stanza,
    upstream_version,
)
from ..config import DebianChangelogWriter, Writer
from ..validation._base import Finding
from ._base import WriteContext


class DebianChangelogImpl:
    name = "debian-changelog"

    def matches(self, writer: Writer) -> bool:
        return isinstance(writer, DebianChangelogWriter)

    def read_version(self, writer: Writer, repo: Path) -> str | None:
        if not isinstance(writer, DebianChangelogWriter):
            return None
        path = repo / writer.file
        if not path.is_file():
            return None
        try:
            top = parse_top_version(path.read_text(encoding="utf-8"))
        except OSError:
            return None
        if not top:
            return None
        # Strip Debian envelope (epoch, -revision) and convert ``~rc1``
        # to semver ``-rc.1`` so :class:`packaging.version.Version` can
        # parse it downstream.
        return from_debian_pre(upstream_version(top))

    def write(self, ctx: WriteContext) -> list[Path]:
        writer = ctx.writer
        assert isinstance(writer, DebianChangelogWriter)
        config = ctx.config
        strategy = config.project.finalize_strategy

        debian_version = format_debian_version(
            ctx.new_version,
            debian_revision=writer.debian_revision,
            epoch=writer.epoch,
        )
        maintainer = _resolve_maintainer(ctx.repo, writer.maintainer)
        stanza = render_stanza(
            package=writer.package or ctx.component_name,
            version=debian_version,
            distribution=writer.distribution,
            urgency=writer.urgency,
            commits=ctx.relevant_commits,
            maintainer=maintainer,
            sections=config.project.changelog_sections,
            bump_rules=config.bump_rules_for(ctx.component_name),
            breaking_title=config.project.breaking_section_title,
            other_title=config.project.other_section_title,
        )

        path = ctx.repo / writer.file
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if ctx.is_finalize and strategy == "promote":
            existing = drop_prerelease_stanzas(existing, ctx.new_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prepend_stanza(existing, stanza), encoding="utf-8")
        return [path]

    def validate(self, writer: Writer, repo: Path) -> Iterator[Finding]:
        if not isinstance(writer, DebianChangelogWriter):
            return
        path = repo / writer.file
        if not path.exists():
            yield Finding(
                level="info",
                check="debian_changelog_missing",
                component=None,
                message=(
                    f"{str(writer.file)!r} does not exist; it will be "
                    "created on the first bump"
                ),
            )
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            yield Finding(
                level="error",
                check="debian_changelog_unreadable",
                component=None,
                message=f"could not read {str(writer.file)!r}: {exc}",
            )
            return
        if parse_top_stanza(text) is None:
            yield Finding(
                level="error",
                check="debian_changelog_unparseable",
                component=None,
                message=(
                    f"{str(writer.file)!r} top stanza is not a valid "
                    "Debian changelog header"
                ),
            )


def _resolve_maintainer(repo: Path, configured: str | None) -> str:
    """Pick a Debian maintainer string ``Name <email>``.

    Priority: explicit config -> ``Maintainer:`` line in
    ``debian/control`` -> ``git config user.{name,email}`` -> placeholder.
    """
    if configured:
        return configured
    control = repo / "debian" / "control"
    if control.is_file():
        for line in control.read_text(encoding="utf-8").splitlines():
            if line.startswith("Maintainer:"):
                return line[len("Maintainer:"):].strip()
    name_proc = subprocess.run(
        ["git", "config", "user.name"],
        cwd=repo, capture_output=True, text=True,
    )
    email_proc = subprocess.run(
        ["git", "config", "user.email"],
        cwd=repo, capture_output=True, text=True,
    )
    name = name_proc.stdout.strip()
    email = email_proc.stdout.strip()
    if name and email:
        return f"{name} <{email}>"
    return "Unknown <unknown@example.com>"
