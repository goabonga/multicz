# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Release-notes, changelog, validate, state and init-detect presenters."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from multicz.cli import presenters
from multicz.cli.results import ChangelogEntry, ValidationReport
from multicz.commits import Commit
from multicz.config import Config
from multicz.state import ComponentState, State
from multicz.validation import Finding


@pytest.fixture
def out(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buffer = io.StringIO()
    monkeypatch.setattr(presenters, "console", Console(file=buffer, width=200, no_color=True))
    return buffer


def _config() -> Config:
    return Config.model_validate({"components": {"api": {"paths": ["src/**"]}}})


def _commit(**overrides) -> Commit:
    fields = {
        "sha": "abcdef1234567890",
        "type": "feat",
        "scope": None,
        "breaking": False,
        "subject": "add thing",
        "body": "",
        "files": ("src/a.py",),
    }
    fields.update(overrides)
    return Commit(**fields)


# ============ release-notes ============


def test_release_notes_empty_json(out: io.StringIO) -> None:
    presenters.render_release_notes_empty(output="json")
    assert json.loads(out.getvalue()) == {"sections": []}


def test_release_notes_empty_text(out: io.StringIO) -> None:
    presenters.render_release_notes_empty(output="text")
    assert "nothing to release" in out.getvalue()


def test_release_notes_no_pending(out: io.StringIO) -> None:
    presenters.render_release_notes_no_pending("api")
    assert "no pending bump for api" in out.getvalue()


# ============ changelog ============


def test_changelog_md_heading_with_since(capsys: pytest.CaptureFixture[str]) -> None:
    entry = ChangelogEntry(component="api", since="api-v1.0.0", relevant=(_commit(),))
    presenters.render_changelog([entry], _config(), output="md")
    assert "## api (since api-v1.0.0)" in capsys.readouterr().out


def test_changelog_text_without_changes(out: io.StringIO) -> None:
    entry = ChangelogEntry(component="api", since="api-v1.0.0", relevant=())
    presenters.render_changelog([entry], _config(), output="text")
    text = out.getvalue()
    assert "## api  (since api-v1.0.0)" in text
    assert "no changes" in text


def test_changelog_text_lists_commits(out: io.StringIO) -> None:
    entry = ChangelogEntry(
        component="api",
        since=None,
        relevant=(_commit(scope="web", breaking=True), _commit(sha="1234567abc", subject="plain")),
    )
    presenters.render_changelog([entry], _config(), output="text")
    text = out.getvalue()
    assert "feat(web)!: add thing  (abcdef1)" in text
    assert "feat: plain  (1234567)" in text


# ============ validate ============


def _finding(level: str, component: str | None = None) -> Finding:
    return Finding(level=level, check="some-check", component=component, message=f"a {level}")


def test_validate_summary_counts_infos(out: io.StringIO) -> None:
    info = _finding("info")
    report = ValidationReport(findings=(info,), errors=(), warnings=(), infos=(info,))
    presenters.render_validate(report, output="text")
    assert "1 info" in out.getvalue()


# ============ state ============


def test_state_missing_json(out: io.StringIO) -> None:
    presenters.render_state_missing(".multicz/state.json", output="json")
    assert json.loads(out.getvalue()) is None


def test_state_missing_text(out: io.StringIO) -> None:
    presenters.render_state_missing(".multicz/state.json", output="text")
    assert ".multicz/state.json not yet written" in out.getvalue()


def test_state_text_lists_components(out: io.StringIO) -> None:
    state = State(
        version=1,
        git_head="f" * 40,
        git_head_short="fffffff",
        timestamp="2025-01-01T00:00:00Z",
        components={
            "api": ComponentState(version="1.0.0", tag="api-v1.0.0"),
            "docs": ComponentState(version="0.1.0"),
        },
    )
    presenters.render_state(state, ".multicz/state.json", output="text")
    text = out.getvalue()
    assert "schema v1" in text
    assert "git_head:  fffffff" in text
    assert "timestamp: 2025-01-01T00:00:00Z" in text
    assert "api: 1.0.0  (api-v1.0.0)" in text
    assert "docs: 0.1.0" in text


# ============ init --detect ============


def _detected(**overrides) -> SimpleNamespace:
    fields = {"paths": [], "bump_files": [], "mirrors": [], "writers": [], "changelog": None}
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_init_detect_text_variants(out: io.StringIO) -> None:
    writer = SimpleNamespace(type="debian_changelog", file=Path("debian/changelog"))
    presenters.render_init_detect(
        {
            "tagged": _detected(),
            "debian": _detected(writers=[writer]),
            "linked": _detected(
                bump_files=[SimpleNamespace(file=Path("pyproject.toml"), key="project.version")],
                mirrors=[
                    SimpleNamespace(file=Path("Chart.yaml"), key="appVersion"),
                    SimpleNamespace(file=Path("VERSION"), key=None),
                ],
            ),
        },
        output="text",
    )
    text = out.getvalue()
    assert "Detected 3 component(s):" in text
    assert "tagged (tag-driven)" in text
    assert "debian (debian/changelog) writers=debian_changelog" in text
    assert "linked (pyproject.toml)" in text
    assert "mirrors → Chart.yaml:appVersion, VERSION" in text
