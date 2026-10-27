# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Presenters for ``multicz bump``, rendered to an in-memory console."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from multicz.cli import presenters
from multicz.cli.results import AppliedBump, BumpResult, GitSummary


@pytest.fixture
def out(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buffer = io.StringIO()
    monkeypatch.setattr(presenters, "console", Console(file=buffer, width=200, no_color=True))
    return buffer


class _Artifact:
    def render(self, *, component: str, version: str) -> str:
        return f"{component}:{version}"


class _Component:
    def __init__(self) -> None:
        self.artifacts = [_Artifact()]


class _BumpConfig:
    def __init__(self) -> None:
        self.components = {"api": _Component()}

    def tag_format_for(self, component: str) -> str:
        return "{component}-v{version}"


def _result(
    *, dry_run: bool = False, bumps: bool = True, git: GitSummary | None = None
) -> BumpResult:
    applied = (AppliedBump("api", "1.0.0", "1.1.0", "minor"),) if bumps else ()
    return BumpResult(
        bumps=applied,
        dry_run=dry_run,
        git=git or GitSummary(),
        changelogs=("CHANGELOG.md",),
    )


FULL_GIT = GitSummary(
    commit_sha="abcdef1234567890",
    tags=("api-v1.1.0",),
    pushed=True,
    signed_commit=True,
    signed_tags=True,
)


def test_bump_empty_json(out: io.StringIO) -> None:
    presenters.render_bump_empty(output="json")
    assert json.loads(out.getvalue()) == {"bumps": {}}


def test_bump_result_json_with_full_git_summary(out: io.StringIO) -> None:
    presenters.render_bump_result(_result(git=FULL_GIT), _BumpConfig(), output="json")
    payload = json.loads(out.getvalue())
    assert payload["git"] == {
        "commit": "abcdef1234567890",
        "tags": ["api-v1.1.0"],
        "signed_tags": "yes",
        "signed_commit": "yes",
        "pushed": "yes",
    }
    assert payload["bumps"]["api"]["artifacts"] == ["api:1.1.0"]


def test_bump_result_text_reports_every_git_side_effect(out: io.StringIO) -> None:
    presenters.render_bump_result(_result(git=FULL_GIT), _BumpConfig(), output="text")
    text = out.getvalue()
    assert "bumped api 1.0.0 → 1.1.0 (minor)" in text
    assert "updated changelog CHANGELOG.md" in text
    assert "committed abcdef1" in text
    assert "tagged api-v1.1.0" in text
    assert "pushed" in text


def test_bump_summary_without_bumps(tmp_path: Path) -> None:
    target = tmp_path / "summary.md"
    presenters.append_bump_summary(target, _result(dry_run=True, bumps=False), _BumpConfig())
    assert target.read_text() == "## Would release\n\n_No bumps pending._\n"


def test_bump_summary_lists_git_details(tmp_path: Path) -> None:
    target = tmp_path / "summary.md"
    presenters.append_bump_summary(target, _result(git=FULL_GIT), _BumpConfig())
    text = target.read_text()
    assert "## Released" in text
    assert "| `api` | `1.0.0` | `1.1.0` | minor | `api-v1.1.0` |" in text
    assert "**Release commit:** `abcdef123456`" in text
    assert "**Tags created:** `api-v1.1.0`" in text
    assert "**Pushed:** yes" in text
    assert "**Signed commit:** yes" in text
    assert "**Signed tags:** yes" in text
