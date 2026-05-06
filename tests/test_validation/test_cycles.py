# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for TriggerCycleCheck and MirrorCycleCheck in isolation."""

from __future__ import annotations

from pathlib import Path

from multicz.config import ComponentMatcher, load_config
from multicz.validation._base import ValidationContext
from multicz.validation.cycles import MirrorCycleCheck, TriggerCycleCheck


def _ctx(repo: Path) -> ValidationContext:
    config = load_config(repo / "multicz.toml")
    return ValidationContext(
        repo=repo, config=config, matcher=ComponentMatcher(config.components)
    )


def test_trigger_cycle_detected(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
    )
    (tmp_path / "multicz.toml").write_text("""
[components.a]
paths = ["a/**"]
triggers = ["b"]

[components.b]
paths = ["b/**"]
triggers = ["a"]
""")
    findings = list(TriggerCycleCheck().run(_ctx(tmp_path)))
    assert findings
    assert findings[0].level == "error"
    assert findings[0].check == "trigger_cycle"
    assert "->" in findings[0].message


def test_mirror_cycle_detected(tmp_path: Path):
    (tmp_path / "a.yaml").write_text("v: 1\n")
    (tmp_path / "b.yaml").write_text("v: 1\n")
    (tmp_path / "multicz.toml").write_text("""
[components.a]
paths = ["a.yaml"]
bump_files = [{ file = "a.yaml", key = "v" }]
mirrors = [{ file = "b.yaml", key = "v" }]

[components.b]
paths = ["b.yaml"]
bump_files = [{ file = "b.yaml", key = "v" }]
mirrors = [{ file = "a.yaml", key = "v" }]
""")
    findings = list(MirrorCycleCheck().run(_ctx(tmp_path)))
    assert findings
    assert findings[0].level == "error"
    assert findings[0].check == "mirror_cycle"
