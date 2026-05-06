# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Changelog rendering for multicz components.

The package is split by output format:

* :mod:`multicz.changelog.bucket` - pure commit filtering / section
  bucketing logic shared by every renderer.
* :mod:`multicz.changelog.markdown` - keep-a-changelog ``CHANGELOG.md``
  rendering (used both as a component's primary changelog and as a
  parallel markdown rendering alongside a ``debian-changelog`` writer).
* :mod:`multicz.changelog.debian` - RFC 5322 stanza rendering for
  ``debian/changelog``, plus the parsing helpers used to read the
  topmost stanza as a version source of truth.

This ``__init__`` re-exports the public API of each submodule so the
same import paths that worked before the package split keep working.
"""

from __future__ import annotations

from .bucket import BucketedCommits, bucket_commits, filter_commits
from .debian import (
    DebianStanza,
    drop_prerelease_stanzas,
    format_debian_version,
    from_debian_pre,
    parse_top_stanza,
    parse_top_version,
    prepend_stanza,
    render_stanza,
    to_debian_pre,
    upstream_version,
)
from .markdown import (
    CascadeEntry,
    insert_section,
    render_body,
    render_section,
    update_changelog_file,
)

__all__ = [
    "BucketedCommits",
    "CascadeEntry",
    "DebianStanza",
    "bucket_commits",
    "drop_prerelease_stanzas",
    "filter_commits",
    "format_debian_version",
    "from_debian_pre",
    "insert_section",
    "parse_top_stanza",
    "parse_top_version",
    "prepend_stanza",
    "render_body",
    "render_section",
    "render_stanza",
    "to_debian_pre",
    "update_changelog_file",
    "upstream_version",
]
