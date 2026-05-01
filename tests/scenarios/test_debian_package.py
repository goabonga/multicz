"""Scenario: Debian source package.

A repo with a ``debian/`` directory and a properly-formatted
``debian/changelog``. Multicz must:

  - read the upstream version from the topmost stanza
  - prepend a new stanza on bump using the conventional commits since
    the last release
  - render pre-releases with the Debian tilde notation (``1.3.0~rc1``)
"""

from __future__ import annotations

from multicz.cli import app

CONFIG = """\
[components.mypkg]
paths = ["debian/**", "src/**"]
format = "debian"

[components.mypkg.debian]
distribution = "unstable"
urgency = "medium"
"""


INITIAL_CHANGELOG = """\
mypkg (1.2.3-1) unstable; urgency=medium

  * Initial release.

 -- scenarios <scenarios@multicz>  Sun, 01 Jan 2023 00:00:00 +0000
"""


def test_feat_prepends_stanza_with_correct_upstream_version(
    make_repo, commit, runner
):
    repo = make_repo({
        "multicz.toml": CONFIG,
        "debian/changelog": INITIAL_CHANGELOG,
        "debian/control": "Source: mypkg\nMaintainer: scenarios <scenarios@multicz>\n",
        "src/main.py": "x = 1\n",
    })
    commit({"src/main.py": "x = 2\n"}, "feat: add login")

    result = runner.invoke(app, ["bump"])
    assert result.exit_code == 0, result.stdout

    text = (repo / "debian/changelog").read_text()
    # Newest stanza on top, older stanza preserved verbatim
    assert text.index("mypkg (1.3.0-1)") < text.index("mypkg (1.2.3-1)")
    assert "feat: Add login" in text


def test_pre_rc_uses_tilde_notation_in_debian_changelog(
    make_repo, commit, runner
):
    repo = make_repo({
        "multicz.toml": CONFIG,
        "debian/changelog": INITIAL_CHANGELOG,
        "src/main.py": "x = 1\n",
    })
    commit({"src/main.py": "x = 2\n"}, "feat: add login")

    runner.invoke(app, ["bump", "--pre", "rc"])
    text = (repo / "debian/changelog").read_text()
    assert "mypkg (1.3.0~rc1-1)" in text
