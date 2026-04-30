from multicz.commits import parse_commit


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
