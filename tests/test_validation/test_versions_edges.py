# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from __future__ import annotations

from pathlib import Path

import pytest

from multicz.config import ComponentMatcher, load_config
from multicz.validation._base import ValidationContext
from multicz.validation.versions import CurrentVersionCheck


def test_unresolvable_version_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "multicz.toml").write_text("""
[components.api]
paths = ["src/**"]
""")
    config = load_config(tmp_path / "multicz.toml")
    ctx = ValidationContext(
        repo=tmp_path, config=config, matcher=ComponentMatcher(config.components)
    )

    def boom(repo, config, name):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("multicz.planner._current_version", boom)

    [finding] = list(CurrentVersionCheck().run(ctx))
    assert finding.level == "error"
    assert finding.check == "version_unreadable"
    assert finding.component == "api"
    assert "kaboom" in finding.message
