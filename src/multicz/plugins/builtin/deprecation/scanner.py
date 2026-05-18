# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Source-tree scanner for deprecation markers.

Two marker shapes are recognised — Python decorator + free-form
comment — so the plugin covers both Python and any other language /
file format (Helm chart, Dockerfile, .toml, etc.).

* **Decorator form** — Python only::

      @deprecated(since="1.2.0", remove_in="3.0.0")
      def old_handler(...): ...

* **Comment form** — language-agnostic::

      # DEPRECATED since=1.2.0 remove_in=3.0.0 — use new_thing instead
      // DEPRECATED since=1.2.0 remove_in=3.0.0
      <!-- DEPRECATED since=1.2.0 remove_in=3.0.0 -->

Both forms must provide ``since`` AND ``remove_in`` as parseable
versions (``packaging.version.Version``). Optional trailing prose
after a ``—``, ``:`` or ``-`` is captured as the marker message and
surfaced in changelog entries / advice lines.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class Deprecation:
    """A single deprecation marker found in the source tree."""

    file: Path
    line: int
    since: Version
    remove_in: Version
    message: str = ""


# Match ``@deprecated(since="1.2.0", remove_in="3.0.0")`` — both quoting
# styles, optional whitespace, optional trailing kwargs we ignore.
_DECORATOR_RE = re.compile(
    r"""@deprecated\(\s*
        (?:                                                # since/remove_in in any order
            (?:since\s*=\s*["']\s*(?P<since1>[^"']+?)\s*["']\s*,?\s*)
            (?:remove_in\s*=\s*["']\s*(?P<remove_in1>[^"']+?)\s*["'])
            |
            (?:remove_in\s*=\s*["']\s*(?P<remove_in2>[^"']+?)\s*["']\s*,?\s*)
            (?:since\s*=\s*["']\s*(?P<since2>[^"']+?)\s*["'])
        )
    """,
    re.VERBOSE,
)

# Match free-form ``DEPRECATED since=1.2 remove_in=3.0`` inside any
# common comment prefix. Trailing message after ``—``/``-``/``:`` is
# optional.
_COMMENT_RE = re.compile(
    r"""(?:\#|//|<!--)\s*
        DEPRECATED
        \s+ since\s*=\s*(?P<since>\S+)
        \s+ remove_in\s*=\s*(?P<remove_in>\S+)
        (?:\s*[—\-:]\s*(?P<message>.+?))?
        (?:\s*-->)?
        \s*$
    """,
    re.VERBOSE,
)


def _safe_version(raw: str) -> Version | None:
    try:
        return Version(raw.strip().rstrip(",)"))
    except InvalidVersion:
        return None


def _scan_file(path: Path) -> Iterator[Deprecation]:
    """Yield every deprecation marker found in ``path``.

    Silently skips files we can't decode as UTF-8 (binaries, encoding
    edge cases) so a stray PNG in a watched dir doesn't crash the
    scan."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()
        if "DEPRECATED" in line:
            m = _COMMENT_RE.search(line)
            if m:
                since = _safe_version(m.group("since"))
                remove_in = _safe_version(m.group("remove_in"))
                if since and remove_in:
                    yield Deprecation(
                        file=path,
                        line=lineno,
                        since=since,
                        remove_in=remove_in,
                        message=(m.group("message") or "").strip(),
                    )
                    continue
        if "@deprecated" in line:
            m = _DECORATOR_RE.search(line)
            if m:
                since_raw = m.group("since1") or m.group("since2")
                remove_in_raw = m.group("remove_in1") or m.group("remove_in2")
                since = _safe_version(since_raw) if since_raw else None
                remove_in = _safe_version(remove_in_raw) if remove_in_raw else None
                if since and remove_in:
                    yield Deprecation(
                        file=path,
                        line=lineno,
                        since=since,
                        remove_in=remove_in,
                        message="",
                    )


def scan_paths(repo: Path, globs: Iterable[str]) -> list[Deprecation]:
    """Walk every glob (rooted at ``repo``) and aggregate markers.

    Globs use the same syntax as :meth:`pathlib.Path.glob`. Duplicates
    that resolve to the same ``(file, line)`` are de-duplicated; order
    is preserved (file, line) for stable CLI output.
    """
    found: dict[tuple[Path, int], Deprecation] = {}
    for pattern in globs:
        for path in repo.glob(pattern):
            if path.is_file():
                for dep in _scan_file(path):
                    found.setdefault((dep.file, dep.line), dep)
    return sorted(found.values(), key=lambda d: (str(d.file), d.line))
