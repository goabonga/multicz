# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from multicz.commits import (
    DEFAULT_BUMP_RULES,
    bump_kind_for,
    parse_commit,
    validate_message,
)


def test_feat_is_minor():
    commit = parse_commit("a", "feat: add login", ("src/a.py",))
    assert commit.type == "feat"
    assert commit.bump_kind == "minor"
    assert not commit.breaking


def test_fix_is_patch():
    commit = parse_commit("a", "fix(api): null pointer", ())
    assert commit.scope == "api"
    assert commit.bump_kind == "patch"


def test_perf_is_patch():
    commit = parse_commit("a", "perf: faster path", ())
    assert commit.bump_kind == "patch"


def test_revert_is_patch():
    commit = parse_commit("a", "revert: feat: add login", ())
    assert commit.type == "revert"
    assert commit.bump_kind == "patch"


def test_revert_with_scope_is_patch():
    commit = parse_commit("a", "revert(api): drop login flow", ())
    assert commit.scope == "api"
    assert commit.bump_kind == "patch"


def test_revert_breaking_is_still_major():
    """An explicit '!' on a revert means the original was breaking and
    re-applying the breaking change. Honour the '!'."""
    commit = parse_commit("a", "revert!: drop the new API", ())
    assert commit.bump_kind == "major"


def test_bang_is_breaking():
    commit = parse_commit("a", "feat!: rewrite", ())
    assert commit.breaking
    assert commit.bump_kind == "major"


def test_breaking_change_footer_is_breaking():
    msg = "feat: x\n\nbody\n\nBREAKING CHANGE: drops py3.11"
    commit = parse_commit("a", msg, ())
    assert commit.breaking
    assert commit.bump_kind == "major"


def test_chore_does_not_bump():
    commit = parse_commit("a", "chore: bump deps", ())
    assert commit.bump_kind is None


def test_non_conventional_is_ignored():
    commit = parse_commit("a", "random message", ())
    assert not commit.is_conventional
    assert commit.bump_kind is None


def test_validate_accepts_conventional():
    assert validate_message("feat(api): add login") is None
    assert validate_message("fix: broken thing\n\nbody") is None
    assert validate_message("feat!: drop py 3.11") is None


def test_validate_rejects_non_conventional():
    error = validate_message("just some text")
    assert error is not None
    assert "conventional" in error.lower() or "header" in error.lower()


def test_validate_rejects_empty():
    assert validate_message("") is not None
    assert validate_message("   \n\n") is not None


def test_validate_rejects_unknown_type():
    error = validate_message("wibble: something")
    assert error is not None
    assert "wibble" in error


def test_validate_skips_merge_and_fixup():
    assert validate_message("Merge branch 'main' into dev") is None
    assert validate_message("fixup! feat: x") is None
    assert validate_message("Revert \"feat: x\"") is None


def test_validate_custom_types():
    assert validate_message("custom: x", allowed_types=("custom", "feat")) is None
    error = validate_message("feat: x", allowed_types=("custom",))
    assert error is not None


# ---------------------------------------------------------------------------
# bump_kind_for: configurable rules
# ---------------------------------------------------------------------------


def test_bump_kind_for_default_rules_match_property():
    """The free function with DEFAULT_BUMP_RULES matches the convenience
    property on Commit."""
    for msg in (
        "feat: x",
        "fix: x",
        "perf: x",
        "revert: x",
        "feat!: x",
        "chore: x",
        "chore!: x",
        "refactor: x",
    ):
        c = parse_commit("a", msg, ())
        assert bump_kind_for(c, DEFAULT_BUMP_RULES) == c.bump_kind, msg


def test_bump_kind_for_custom_rule_promotes_refactor_to_patch():
    """Adding ``refactor = "patch"`` makes refactor commits bump patch."""
    c = parse_commit("a", "refactor: split module", ())
    rules = {**DEFAULT_BUMP_RULES, "refactor": "patch"}
    assert bump_kind_for(c, rules) == "patch"


def test_bump_kind_for_explicit_none_silences_breaking_too():
    """``feat = "none"`` drops feat! as well — the legacy ignored_types
    semantics: explicit opt-out beats the breaking marker."""
    c = parse_commit("a", "feat!: drop py3.11", ())
    rules = {**DEFAULT_BUMP_RULES, "feat": "none"}
    assert bump_kind_for(c, rules) is None


def test_bump_kind_for_absent_type_keeps_breaking_as_major():
    """A type with no rule (e.g. chore by default) still bumps major
    when breaking — Conventional Commits default."""
    c = parse_commit("a", "chore!: rip out legacy", ())
    assert bump_kind_for(c, DEFAULT_BUMP_RULES) == "major"


def test_bump_kind_for_custom_type_bumps_per_rule():
    """A user-defined type like ``infra`` bumps per its rule."""
    c = parse_commit("a", "infra: rotate creds", ())
    assert bump_kind_for(c, {"infra": "patch"}) == "patch"
    assert bump_kind_for(c, {"infra": "minor"}) == "minor"
