# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Direct tests of the output presenters, rendered to an in-memory console."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from multicz.cli import presenters
from multicz.plugins.protocol import Severity, Violation


@pytest.fixture
def out(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buffer = io.StringIO()
    monkeypatch.setattr(presenters, "console", Console(file=buffer, width=200, no_color=True))
    return buffer


class _Plugin:
    def __init__(self, name: str) -> None:
        self.name = name


def test_plugins_list_without_plugins(out: io.StringIO) -> None:
    presenters.render_plugins_list([], {}, output="text")
    assert "no plugins discovered" in out.getvalue()
    assert "multicz.plugins" in out.getvalue()


def test_plugins_list_config_cells(out: io.StringIO) -> None:
    presenters.render_plugins_list(
        [_Plugin("tuned"), _Plugin("plain"), _Plugin("off"), _Plugin("idle")],
        {"tuned": {"level": 3}, "plain": {}, "off": {"enabled": False}},
        output="text",
    )
    text = out.getvalue()
    assert "level=3" in text
    assert "(defaults)" in text
    assert "disabled" in text
    assert "not in multicz.toml" in text


def test_plugin_advice_json(out: io.StringIO) -> None:
    presenters.render_plugin_advice(["a", "b"], output="json")
    assert json.loads(out.getvalue()) == {"advice": ["a", "b"]}


def test_plugin_advice_text(out: io.StringIO) -> None:
    presenters.render_plugin_advice(["first tip"], output="text")
    assert "first tip" in out.getvalue()


def test_plugin_advice_text_empty_prints_nothing(out: io.StringIO) -> None:
    presenters.render_plugin_advice([], output="text")
    assert out.getvalue() == ""


VIOLATIONS = [
    Violation(Severity.info, "fyi", plugin="p"),
    Violation(Severity.warning, "careful", file=Path("a.py"), plugin="p"),
    Violation(Severity.error, "broken", file=Path("b.py"), line=7, component="api", plugin="p"),
]


def test_plugin_violations_json(out: io.StringIO) -> None:
    presenters.render_plugin_violations(VIOLATIONS, output="json")
    payload = json.loads(out.getvalue())["violations"]
    assert payload[0]["file"] is None
    assert payload[2] == {
        "severity": "error",
        "message": "broken",
        "plugin": "p",
        "component": "api",
        "file": "b.py",
        "line": 7,
    }


def test_plugin_violations_text_orders_by_severity(out: io.StringIO) -> None:
    presenters.render_plugin_violations(VIOLATIONS, output="text")
    text = out.getvalue()
    assert text.index("broken") < text.index("careful") < text.index("fyi")
    assert "(b.py:7)" in text
    assert "(a.py)" in text
    assert "[api]" in text
    assert "(from p)" in text
