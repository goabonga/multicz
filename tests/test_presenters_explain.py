# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz explain`` and ``multicz artifacts`` presenters."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from rich.console import Console

from multicz.cli import presenters
from multicz.planner import CommitReason, ManualReason, MirrorReason, TriggerReason


@pytest.fixture
def out(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buffer = io.StringIO()
    monkeypatch.setattr(presenters, "console", Console(file=buffer, width=200, no_color=True))
    return buffer


def _bump(*reasons, pre: str | None = None, finalize: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        current="1.0.0",
        next="1.1.0",
        kind="minor",
        pre=pre,
        finalize=finalize,
        reasons=list(reasons),
    )


def test_explain_without_pending_bump(out: io.StringIO) -> None:
    presenters.render_explain("api", None)
    assert "no bump pending" in out.getvalue()


def test_explain_pre_release_and_finalize(out: io.StringIO) -> None:
    presenters.render_explain("api", _bump(ManualReason("forced"), pre="rc", finalize=True))
    text = out.getvalue()
    assert "Pre-release:     rc" in text
    assert "Finalize:        yes" in text
    assert "1. forced" in text


def test_explain_commit_reason_details(out: io.StringIO) -> None:
    reason = CommitReason(
        sha="abcdef1234",
        type="feat",
        scope="web",
        breaking=True,
        subject="add thing",
        files=("src/a.py", "src/b.py"),
        bump_kind="patch",
        original_kind="minor",
    )
    presenters.render_explain("api", _bump(reason))
    text = out.getvalue()
    assert "Type:  feat(web) → patch" in text
    assert "Demoted from minor" in text
    assert "Breaking: yes" in text
    assert "- src/a.py" in text
    assert "- src/b.py" in text


def test_explain_trigger_reason(out: io.StringIO) -> None:
    presenters.render_explain("chart", _bump(TriggerReason("api", "minor")))
    text = out.getvalue()
    assert "Upstream:      api" in text
    assert "Upstream kind: minor" in text


def test_explain_mirror_reason_with_and_without_key(out: io.StringIO) -> None:
    presenters.render_explain(
        "chart",
        _bump(
            MirrorReason("api", "Chart.yaml", "appVersion"),
            MirrorReason("api", "VERSION", None),
        ),
    )
    text = out.getvalue()
    assert "Wrote:    Chart.yaml:appVersion" in text
    assert "Wrote:    VERSION" in text


def test_artifacts_text_lists_declared_and_empty(out: io.StringIO) -> None:
    presenters.render_artifacts(
        {
            "api": {"version": "1.0.0", "artifacts": [{"type": "docker", "ref": "app:1.0.0"}]},
            "docs": {"version": "0.1.0", "artifacts": []},
        },
        output="text",
    )
    text = out.getvalue()
    assert "api (1.0.0)" in text
    assert "app:1.0.0" in text
    assert "docs: no artifacts declared" in text


def test_artifacts_json(out: io.StringIO) -> None:
    presenters.render_artifacts({"api": {"version": "1.0.0", "artifacts": []}}, output="json")
    assert '"api"' in out.getvalue()
