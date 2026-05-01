"""Map repository file paths to declared components.

Each component owns a set of gitignore-style glob ``paths`` and optional
``exclude_paths``. A file is assigned to the *first* component (in declaration
order) whose include patterns match and whose exclude patterns do not.
Components later in the config can act as a generic catch-all by using a
broad pattern like ``"**"``.
"""

from __future__ import annotations

from collections.abc import Iterable

import pathspec

from .config import Component


class ComponentMatcher:
    def __init__(self, components: dict[str, Component]) -> None:
        self._order: list[str] = list(components)
        self._include: dict[str, pathspec.PathSpec] = {}
        self._exclude: dict[str, pathspec.PathSpec] = {}
        for name, comp in components.items():
            self._include[name] = pathspec.PathSpec.from_lines("gitignore", comp.paths)
            self._exclude[name] = pathspec.PathSpec.from_lines(
                "gitignore", comp.exclude_paths
            )

    def match(self, path: str) -> str | None:
        """Return the component owning ``path``, or ``None`` if unowned.

        First-match semantics: when several components claim the same file,
        the one declared earliest in the config wins. Use :meth:`match_all`
        when the project's ``overlap_policy = "all"`` is in effect.
        """
        for name in self._order:
            if self._include[name].match_file(path) and not self._exclude[name].match_file(path):
                return name
        return None

    def match_all(self, path: str) -> list[str]:
        """Return *every* component whose include patterns match ``path``.

        Used by the ``"all"`` overlap policy so a file shared between
        several components bumps each of them rather than just the first.
        """
        return [
            name
            for name in self._order
            if self._include[name].match_file(path)
            and not self._exclude[name].match_file(path)
        ]

    def group(self, paths: Iterable[str]) -> dict[str, set[str]]:
        """Group ``paths`` by owning component. Unowned paths are silently dropped."""
        owned: dict[str, set[str]] = {}
        for path in paths:
            name = self.match(path)
            if name is not None:
                owned.setdefault(name, set()).add(path)
        return owned
