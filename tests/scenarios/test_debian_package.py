# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

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

[[components.mypkg.writers]]
type = "debian-changelog"
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


CONFIG_DUAL = """\
[components.mypkg]
paths     = ["debian/**", "src/**"]
changelog = "CHANGELOG.md"

[[components.mypkg.writers]]
type         = "debian-changelog"
distribution = "unstable"
urgency      = "medium"
"""


def test_dual_changelog_writes_both_debian_stanza_and_markdown(
    make_repo, commit, runner
):
    """A debian-format component with a top-level `changelog` writes
    BOTH the Debian stanza (version source of truth) and a
    keep-a-changelog Markdown file at every bump."""
    repo = make_repo({
        "multicz.toml": CONFIG_DUAL,
        "debian/changelog": INITIAL_CHANGELOG,
        "debian/control": "Source: mypkg\nMaintainer: scenarios <scenarios@multicz>\n",
        "src/main.py": "x = 1\n",
    })
    commit({"src/main.py": "x = 2\n"}, "feat: add login")

    result = runner.invoke(app, ["bump"])
    assert result.exit_code == 0, result.stdout

    # Debian stanza updated as before.
    deb = (repo / "debian/changelog").read_text()
    assert "mypkg (1.3.0-1)" in deb
    assert "feat: Add login" in deb

    # Markdown CHANGELOG.md created in parallel with H2 + Features
    # bucket (matching keep-a-changelog conventions used by the default
    # format).
    md = (repo / "CHANGELOG.md").read_text()
    assert "## [1.3.0]" in md
    assert "### Features" in md
    assert "add login" in md
    # Default cascade section must NOT appear (mirrors are forbidden in
    # debian mode, so cascades are never relevant).
    assert "### Dependencies" not in md


def test_dual_changelog_filters_chore_in_both_files(
    make_repo, commit, runner
):
    """The chore/test/ci filter applies symmetrically: both the Debian
    stanza and the Markdown CHANGELOG.md drop non-section commit types
    by default."""
    repo = make_repo({
        "multicz.toml": CONFIG_DUAL,
        "debian/changelog": INITIAL_CHANGELOG,
        "src/main.py": "x = 1\n",
    })
    commit({"src/main.py": "x = 2\n"}, "feat: add login")
    commit({"src/main.py": "x = 3\n"}, "chore: tidy imports")
    commit({"src/main.py": "x = 4\n"}, "test: add fixture")

    runner.invoke(app, ["bump"])

    deb = (repo / "debian/changelog").read_text()
    md = (repo / "CHANGELOG.md").read_text()
    for needle in ("Add login", "feat: Add login"):
        assert needle in deb if needle.startswith("feat") else needle.lower() in md.lower()
    assert "tidy imports" not in deb
    assert "tidy imports" not in md
    assert "Add fixture" not in deb
    assert "fixture" not in md.lower()


CONFIG_PACKAGE_OVERRIDE = """\
[components.api]
paths      = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[[components.api.writers]]
type    = "debian-changelog"
file    = "debian/changelog"
package = "shomer-api"
"""


def test_writer_package_override_used_in_stanza_header(
    make_repo, commit, runner
):
    """When ``package`` is set on the writer, the rendered stanza uses
    that name in the header (matching debian/control's Source:),
    even though the multicz component is just ``api``."""
    repo = make_repo({
        "multicz.toml": CONFIG_PACKAGE_OVERRIDE,
        "pyproject.toml": (
            "[project]\nname = \"shomer-api\"\nversion = \"1.2.3\"\n"
        ),
        "src/main.py": "x = 1\n",
        "debian/changelog": (
            "shomer-api (1.2.3-1) unstable; urgency=medium\n"
            "\n"
            "  * Initial release.\n"
            "\n"
            " -- scenarios <scenarios@multicz>  "
            "Sun, 01 Jan 2023 00:00:00 +0000\n"
        ),
    })
    commit({"src/main.py": "x = 2\n"}, "feat: add login")

    result = runner.invoke(app, ["bump"])
    assert result.exit_code == 0, result.stdout

    text = (repo / "debian/changelog").read_text()
    # New stanza must use "shomer-api", not "api" (the component name).
    assert text.startswith("shomer-api (1.3.0-1)")
    assert "api (1.3.0-1)" not in text.replace("shomer-api (1.3.0-1)", "")
