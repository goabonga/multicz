# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover name de-duplication past the first suffix."""

from pathlib import Path

from multicz.discovery.context import DiscoveryContext


def test_unique_appends_counter_when_suffixed_name_is_taken(tmp_path: Path) -> None:
    ctx = DiscoveryContext(repo=tmp_path)
    assert ctx.unique("app", "py") == "app"
    assert ctx.unique("app", "py") == "app-py"
    assert ctx.unique("app", "py") == "app-py-2"
    assert ctx.unique("app", "py") == "app-py-3"
