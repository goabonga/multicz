# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""PluginValidationCheck: plugin validate violations become findings."""

from __future__ import annotations

from pathlib import Path

from multicz.config import ComponentMatcher, load_config
from multicz.plugins import BasePlugin, PluginRegistry, Severity, Violation
from multicz.validation import CHECKS, PluginValidationCheck, ValidationContext


class GraphPlugin(BasePlugin):
    name = "graph"

    def validate(self, ctx):
        return [
            Violation(Severity.error, "go list failed", component="api"),
            Violation(Severity.warning, "stale entry", file=Path("go.mod"), line=3),
        ]


def _context(tmp_path: Path, plugins: str) -> ValidationContext:
    (tmp_path / "multicz.toml").write_text('[components.api]\npaths = ["src/**"]\n' + plugins)
    config = load_config(tmp_path / "multicz.toml")
    matcher = ComponentMatcher(config.components)
    return ValidationContext(repo=tmp_path, config=config, matcher=matcher)


def test_violations_become_findings_at_the_same_level(tmp_path: Path):
    ctx = _context(tmp_path, "\n[plugins.graph]\n")
    findings = list(PluginValidationCheck(PluginRegistry([GraphPlugin()])).run(ctx))
    assert [(f.level, f.check, f.component, f.message) for f in findings] == [
        ("error", "plugin:graph", "api", "go list failed"),
        ("warning", "plugin:graph", None, "go.mod:3: stale entry"),
    ]


def test_an_inactive_plugin_is_not_asked(tmp_path: Path):
    ctx = _context(tmp_path, "")
    assert list(PluginValidationCheck(PluginRegistry([GraphPlugin()])).run(ctx)) == []


def test_validate_runs_the_plugin_check():
    assert any(isinstance(check, PluginValidationCheck) for check in CHECKS)
