# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from packaging.version import Version

from multicz.planner.plan import PlannedBump, _stronger


def test_stronger_keeps_first_when_second_is_none():
    assert _stronger("minor", None) == "minor"
    assert _stronger(None, "patch") == "patch"
    assert _stronger(None, None) is None


def test_planned_bump_next_version_is_parsed_next():
    bump = PlannedBump(component="api", current=Version("1.2.3"), kind="minor")
    assert bump.next_version == Version("1.3.0")
