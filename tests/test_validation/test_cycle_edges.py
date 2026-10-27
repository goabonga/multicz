# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from multicz.validation._cycle import _find_cycle


def test_edges_to_unknown_nodes_are_ignored():
    assert _find_cycle({"a": ["ghost"]}) is None


def test_cycle_ignores_unknown_nodes_but_still_found():
    assert _find_cycle({"a": ["ghost", "b"], "b": ["a"]}) == ["a", "b"]
