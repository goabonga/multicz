# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover Debian discovery read failures and name de-duplication."""

from pathlib import Path

import pytest

from multicz.config import Component
from multicz.discovery.debian import _debian_unique, _detect_debian


def test_unreadable_changelog_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "debian").mkdir()
    (tmp_path / "debian" / "changelog").write_text("x")

    def boom(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("denied")

    monkeypatch.setattr(Path, "read_text", boom)
    components: dict[str, Component] = {}
    _detect_debian(tmp_path, components)
    assert components == {}


def test_debian_unique_counts_past_taken_suffix() -> None:
    assert _debian_unique("pkg", set()) == "pkg"
    assert _debian_unique("pkg", {"pkg"}) == "pkg-deb"
    assert _debian_unique("pkg", {"pkg", "pkg-deb"}) == "pkg-deb-2"
    assert _debian_unique("pkg", {"pkg", "pkg-deb", "pkg-deb-2"}) == "pkg-deb-3"
