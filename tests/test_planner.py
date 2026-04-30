from packaging.version import Version

from multicz.planner import aggregate_kind, bump_version


def test_bump_patch():
    assert bump_version(Version("1.2.3"), "patch") == Version("1.2.4")


def test_bump_minor_resets_patch():
    assert bump_version(Version("1.2.3"), "minor") == Version("1.3.0")


def test_bump_major_resets_minor_and_patch():
    assert bump_version(Version("1.2.3"), "major") == Version("2.0.0")


def test_aggregate_picks_strongest():
    assert aggregate_kind(["patch", "minor"]) == "minor"
    assert aggregate_kind(["minor", "major"]) == "major"
    assert aggregate_kind(["major", "patch"]) == "major"


def test_aggregate_ignores_none():
    assert aggregate_kind([None, "patch"]) == "patch"
    assert aggregate_kind([None, None]) is None
