# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Built-in upstream-notes plugin.

Enriches a downstream component's changelog / release notes with a
per-upstream section listing the commits merged since the last time
this component was released. Useful for Terraform-style ``depends_on``
chains where a deploy pipeline lands *after* the upstream release, so
the downstream tag naturally ships whatever was tagged upstream in the
meantime.

See :mod:`multicz.plugins.builtin.upstream_notes.plugin` for the
public :class:`UpstreamNotesPlugin` entry point.
"""

from .plugin import UpstreamNotesPlugin

__all__ = ["UpstreamNotesPlugin"]
