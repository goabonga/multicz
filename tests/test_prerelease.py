"""Tests for the --pre / --finalize release-candidate flow."""

from packaging.version import Version

from multicz.planner import compute_next


def test_pep440_scheme_renders_canonical_form():
    assert (
        compute_next(Version("1.2.3"), "minor", pre="rc", scheme="pep440")
        == "1.3.0rc1"
    )
    assert (
        compute_next(Version("1.2.3"), "patch", pre="alpha", scheme="pep440")
        == "1.2.4a1"
    )
    assert (
        compute_next(Version("1.2.3"), "major", pre="beta", scheme="pep440")
        == "2.0.0b1"
    )


def test_pep440_scheme_increments_in_canonical_form():
    # current is 1.3.0rc1 (PEP 440), next pre rc -> 1.3.0rc2 (still PEP 440)
    assert (
        compute_next(Version("1.3.0rc1"), "minor", pre="rc", scheme="pep440")
        == "1.3.0rc2"
    )


def test_pep440_scheme_finalizes_to_plain_version():
    assert (
        compute_next(Version("1.3.0rc1"), "minor", finalize=True, scheme="pep440")
        == "1.3.0"
    )


def test_pep440_compact_label_aliases():
    # 'alpha' -> 'a', 'beta' -> 'b', 'c' -> 'rc'
    assert compute_next(Version("1.0.0"), "minor", pre="alpha", scheme="pep440") == "1.1.0a1"
    assert compute_next(Version("1.0.0"), "minor", pre="beta", scheme="pep440") == "1.1.0b1"
    assert compute_next(Version("1.0.0"), "minor", pre="c", scheme="pep440") == "1.1.0rc1"


def test_no_pre_no_finalize_regular_bump():
    assert compute_next(Version("1.2.3"), "minor") == "1.3.0"
    assert compute_next(Version("1.2.3"), "patch") == "1.2.4"
    assert compute_next(Version("1.2.3"), "major") == "2.0.0"


def test_pre_label_enters_cycle_from_release():
    assert compute_next(Version("1.2.3"), "minor", pre="rc") == "1.3.0-rc.1"
    assert compute_next(Version("1.2.3"), "patch", pre="alpha") == "1.2.4-alpha.1"
    assert compute_next(Version("1.2.3"), "major", pre="beta") == "2.0.0-beta.1"


def test_pre_label_increments_counter_in_same_cycle():
    assert compute_next(Version("1.3.0-rc.1"), "minor", pre="rc") == "1.3.0-rc.2"
    assert compute_next(Version("1.3.0-rc.5"), "patch", pre="rc") == "1.3.0-rc.6"
    # kind is irrelevant within a cycle — target stays
    assert compute_next(Version("1.3.0-rc.1"), "major", pre="rc") == "1.3.0-rc.2"


def test_pre_label_switch_resets_counter():
    assert compute_next(Version("1.3.0-alpha.5"), "minor", pre="rc") == "1.3.0-rc.1"
    assert compute_next(Version("1.3.0-rc.3"), "minor", pre="beta") == "1.3.0-beta.1"


def test_pep440_aliases_collapse_into_same_cycle():
    # 'c' and 'rc' alias in PEP 440 -> same cycle
    assert compute_next(Version("1.3.0c1"), "minor", pre="rc") == "1.3.0-rc.2"
    # 'a' and 'alpha' alias
    assert compute_next(Version("1.3.0a1"), "minor", pre="alpha") == "1.3.0-alpha.2"
    # 'b' and 'beta' alias
    assert compute_next(Version("1.3.0b3"), "minor", pre="beta") == "1.3.0-beta.4"


def test_no_pre_on_prerelease_auto_finalizes():
    assert compute_next(Version("1.3.0-rc.1"), "minor") == "1.3.0"
    assert compute_next(Version("1.3.0-rc.5"), "patch") == "1.3.0"
    # kind is ignored — finalising means dropping the suffix, period
    assert compute_next(Version("1.3.0-rc.1"), "major") == "1.3.0"


def test_explicit_finalize_works_on_prerelease():
    assert compute_next(Version("1.3.0-rc.1"), "patch", finalize=True) == "1.3.0"


def test_explicit_finalize_on_release_falls_back_to_regular_bump():
    assert compute_next(Version("1.2.3"), "minor", finalize=True) == "1.3.0"


def test_compute_next_round_trips_through_version():
    """The string we produce must parse back into a comparable Version."""
    rc = compute_next(Version("1.2.3"), "minor", pre="rc")
    assert Version(rc) > Version("1.2.3")
    final = compute_next(Version(rc), "patch")  # no --pre -> finalize
    assert Version(final) == Version("1.3.0")
    assert Version(final) > Version(rc)


def test_full_rc_cycle():
    """Walk a complete release-candidate workflow end-to-end."""
    v = "1.2.3"
    # Cut first RC after a feat commit
    v = compute_next(Version(v), "minor", pre="rc")
    assert v == "1.3.0-rc.1"
    # More commits -> next RC
    v = compute_next(Version(v), "patch", pre="rc")
    assert v == "1.3.0-rc.2"
    # QA approves -> release
    v = compute_next(Version(v), "patch")
    assert v == "1.3.0"
    # Future patch
    v = compute_next(Version(v), "patch")
    assert v == "1.3.1"
