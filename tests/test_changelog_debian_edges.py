# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

from dataclasses import replace
from datetime import datetime

from multicz.changelog import drop_prerelease_stanzas, prepend_stanza, render_stanza
from multicz.commits import parse_commit

TWO_RC = """\
pkg (1.3.0~rc2-1) unstable; urgency=medium

  * Second rc.

 -- A <a@b>  Mon, 15 Jan 2024 12:34:56 +0000

pkg (1.3.0~rc1-1) unstable; urgency=medium

  * First rc.

 -- A <a@b>  Sun, 14 Jan 2024 12:34:56 +0000

pkg (1.2.0-1) unstable; urgency=medium

  * Older.

 -- A <a@b>  Sat, 13 Jan 2024 12:34:56 +0000
"""


def test_drop_prerelease_stanzas_removes_matching_rcs():
    out = drop_prerelease_stanzas(TWO_RC, "1.3.0")
    assert "rc1" not in out
    assert "rc2" not in out
    assert "pkg (1.2.0-1)" in out


def test_drop_prerelease_stanzas_all_dropped_returns_empty():
    only_rc = TWO_RC.split("pkg (1.2.0-1)")[0]
    assert drop_prerelease_stanzas(only_rc, "1.3.0") == ""


def test_drop_prerelease_stanzas_keeps_trailing_text_and_adds_newline():
    text = "pkg (1.2.0-1) unstable; urgency=low\n\n  * x\n\n -- A <a@b>  d\ntrailing"
    out = drop_prerelease_stanzas(text, "1.3.0")
    assert out.endswith("trailing\n")


def test_drop_prerelease_stanzas_skips_blank_remainder():
    out = drop_prerelease_stanzas(TWO_RC + "\n\n", "1.3.0")
    assert out.strip().startswith("pkg (1.2.0-1)")
    assert "rc" not in out


def test_render_stanza_naive_datetime_assumed_utc():
    text = render_stanza(
        package="p",
        version="1.0.0-1",
        maintainer="x <x@y>",
        when=datetime(2024, 1, 15, 12, 0, 0),
    )
    assert "+0000" in text


def test_render_stanza_empty_subject_bullet():
    commit = replace(parse_commit("a", "feat: x", ()), subject="")
    text = render_stanza(package="p", version="1-1", commits=[commit], maintainer="x <x@y>")
    assert "  * feat: \n" in text


def test_prepend_stanza_adds_missing_trailing_newlines():
    assert prepend_stanza("old", "new") == "new\n\nold\n"


def test_prepend_stanza_into_blank_existing_returns_stanza():
    assert prepend_stanza("  \n", "new") == "new\n"
