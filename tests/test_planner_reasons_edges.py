# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from multicz.planner.reasons import (
    CommitReason,
    ManualReason,
    MirrorReason,
    NonConventionalReason,
    TriggerReason,
)


def test_commit_reason_summary_shows_demotion():
    reason = CommitReason(
        sha="abcdef1234",
        type="feat",
        scope="web",
        breaking=False,
        subject="add thing",
        files=("a.py",),
        bump_kind="patch",
        original_kind="minor",
    )
    assert reason.summary() == "abcdef1 feat(web): add thing [demoted: minor -> patch]"


def test_trigger_reason_summary():
    assert TriggerReason("core", "minor").summary() == "triggered by core (minor)"


def test_mirror_reason_summary_with_and_without_key():
    assert MirrorReason("api", "v.yaml", "version").summary() == (
        "mirror cascade from api (v.yaml:version)"
    )
    assert MirrorReason("api", "VERSION", None).summary() == "mirror cascade from api (VERSION)"


def test_manual_reason_summary_is_note():
    assert ManualReason("--force api:minor").summary() == "--force api:minor"


def test_non_conventional_reason_summary():
    reason = NonConventionalReason(sha="abcdef1234", subject="did stuff", files=("a",))
    assert reason.summary() == "abcdef1 (non-conventional): did stuff"
    assert reason.to_dict() == {
        "kind": "non_conventional",
        "sha": "abcdef1234",
        "subject": "did stuff",
        "files": ["a"],
        "bump_kind": "patch",
    }
