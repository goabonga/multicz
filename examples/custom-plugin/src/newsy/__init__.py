# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""newsy — collect news fragments under ``changes.d/`` and emit them as
changelog sections (towncrier-flavoured).

The plugin is a worked example of how to implement the ``multicz``
plugin Protocol. It exercises all three hooks:

* :meth:`post_plan` — gate the bump when no fragments are present
  (optional, controlled by ``require_fragment_for_bump``).
* :meth:`enrich_changelog` — group fragments by ``<type>`` and emit
  one section per group.
* :meth:`status_lines` — surface a one-line summary in ``multicz
  status`` / ``multicz plan`` so the gate isn't a surprise at bump
  time.

Fragment convention::

    changes.d/<id>.<type>.md

* ``<id>``   — anything unique (PR number, slug, timestamp).
* ``<type>`` — drives the changelog section title; unknown types are
  Title-cased so users can drop a new bucket without touching the
  plugin.
* file body — one paragraph of free-form Markdown; newlines are
  collapsed to single spaces so the result renders as one bullet.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

# Third-party plugins import the public surface of the plugin module.
# The two things you need are :class:`BasePlugin` (no-op defaults so
# you only implement the hooks you care about) and the data classes
# returned from hooks.
from multicz.plugins import (
    BasePlugin,
    ChangelogEntry,
    Severity,
    Violation,
)

if TYPE_CHECKING:
    from multicz.plugins import PluginContext


# Title of the rendered section for known fragment types. Unknown types
# fall back to ``type.title()`` — the renderer doesn't care.
_SECTION_TITLES = {
    "feat": "Features",
    "fix": "Fixes",
    "breaking": "Breaking Changes",
    "doc": "Documentation",
    "chore": "Misc",
}


class NewsyPlugin(BasePlugin):
    """Plugin entry point registered under ``multicz.plugins``."""

    # ``name`` is required. It must match the entry-point key declared
    # in pyproject.toml AND the ``[plugins.<name>]`` section in the
    # consumer's multicz.toml.
    name = "newsy"

    # ------------------------------------------------------------------
    # Config parsing — every key has a default so an empty
    # ``[plugins.newsy]`` section is the minimal opt-in.
    # ------------------------------------------------------------------

    def _directory(self, ctx: PluginContext) -> Path:
        return ctx.repo / ctx.plugin_config.get("directory", "changes.d")

    def _ext(self, ctx: PluginContext) -> str:
        return ctx.plugin_config.get("extension", ".md")

    def _require(self, ctx: PluginContext) -> bool:
        return bool(ctx.plugin_config.get("require_fragment_for_bump", True))

    def _fragments(self, ctx: PluginContext) -> dict[str, list[Path]]:
        """Group fragments by ``<type>``. Empty if the directory is
        missing — a brand-new project hasn't created it yet, and that's
        a perfectly valid state."""
        out: dict[str, list[Path]] = defaultdict(list)
        directory = self._directory(ctx)
        ext = self._ext(ctx)
        if not directory.is_dir():
            return out
        for path in sorted(directory.iterdir()):
            if not path.is_file() or not path.name.endswith(ext):
                continue
            stem = path.name[: -len(ext)]
            if "." not in stem:
                continue
            _, type_name = stem.rsplit(".", 1)
            out[type_name].append(path)
        return out

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def post_plan(self, ctx: PluginContext) -> list[Violation]:
        """Refuse to bump when zero fragments are present (and the
        gate isn't disabled)."""
        if not self._require(ctx):
            return []
        if self._fragments(ctx):
            return []
        return [
            Violation(
                severity=Severity.error,
                # Note: Rich's markup parser interprets ``[…]``, so we
                # backslash-escape the opening bracket of the TOML section
                # so it renders verbatim in the CLI.
                message=(
                    f"no changelog fragments under "
                    f"{self._directory(ctx).name}/ — add at least one "
                    "<id>.<type>.md file or set "
                    "``require_fragment_for_bump = false`` under "
                    "\\[plugins.newsy]"
                ),
                plugin=self.name,
            )
        ]

    def enrich_changelog(
        self, ctx: PluginContext, component: str
    ) -> list[ChangelogEntry]:
        """Emit one section per fragment ``<type>``. Multi-line fragments
        are collapsed to single-line bullets so the markdown stays a
        list."""
        fragments = self._fragments(ctx)
        if not fragments:
            return []
        entries: list[ChangelogEntry] = []
        for type_name, paths in fragments.items():
            lines: list[str] = []
            for path in paths:
                text = path.read_text(encoding="utf-8").strip()
                lines.append(" ".join(text.split()))
            section = _SECTION_TITLES.get(type_name, type_name.title())
            entries.append(
                ChangelogEntry(
                    section=section,
                    component=component,
                    lines=tuple(lines),
                )
            )
        return entries

    def status_lines(self, ctx: PluginContext) -> list[str]:
        """One line per status, advertising the upcoming gate result."""
        fragments = self._fragments(ctx)
        if not fragments:
            verdict = "bump will FAIL" if self._require(ctx) else "bump will still proceed"
            return [
                f"newsy: no fragments under {self._directory(ctx).name}/ "
                f"({verdict})"
            ]
        count = sum(len(v) for v in fragments.values())
        groups = ", ".join(
            f"{len(v)} {t}" for t, v in sorted(fragments.items())
        )
        plural = "s" if count != 1 else ""
        return [f"newsy: {count} fragment{plural} ({groups})"]
