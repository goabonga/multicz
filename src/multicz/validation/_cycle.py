# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Iterative DFS cycle finder shared by trigger and mirror checks."""

from __future__ import annotations

from collections.abc import Iterable

_WHITE, _GRAY, _BLACK = 0, 1, 2


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Iterative DFS cycle finder. Returns the cycle nodes or ``None``."""
    color = dict.fromkeys(graph, _WHITE)

    def dfs(start: str) -> list[str] | None:
        stack: list[tuple[str, Iterable[str], list[str]]] = [
            (start, iter(graph.get(start, [])), [start])
        ]
        color[start] = _GRAY
        while stack:
            node, neighbors, path = stack[-1]
            try:
                nxt = next(neighbors)
            except StopIteration:
                color[node] = _BLACK
                stack.pop()
                continue
            if nxt not in color:
                continue
            if color[nxt] == _GRAY:
                idx = path.index(nxt)
                return path[idx:]
            if color[nxt] == _WHITE:
                color[nxt] = _GRAY
                stack.append((nxt, iter(graph.get(nxt, [])), [*path, nxt]))
        return None

    for node in graph:
        if color[node] == _WHITE:
            result = dfs(node)
            if result:
                return result
    return None
