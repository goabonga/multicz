# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Edge cases of the ``debian-changelog`` writer impl and the registry."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from multicz.config import DebianChangelogWriter, load_config
from multicz.writers import WriteContext, impl_for
from multicz.writers import debian_changelog as dc
from multicz.writers.debian_changelog import DebianChangelogImpl

_CONFIG = """
[project]
finalize_strategy = "promote"

[components.mypkg]
paths = ["debian/**"]

[[components.mypkg.writers]]
type = "debian-changelog"
maintainer = "Me <me@example.com>"
"""

_OLD = """\
mypkg (1.0.0~rc1-1) UNRELEASED; urgency=medium

  * rc.

 -- Me <me@example.com>  Mon, 15 Jan 2024 12:34:56 +0000
"""


class _NotADebianWriter:
    pass


def test_impl_for_unknown_writer_raises():
    with pytest.raises(LookupError, match="no WriterImpl"):
        impl_for(_NotADebianWriter())  # type: ignore[arg-type]


def test_read_version_ignores_foreign_writer(tmp_path: Path):
    impl = DebianChangelogImpl()
    assert impl.read_version(_NotADebianWriter(), tmp_path) is None  # type: ignore[arg-type]


def test_read_version_returns_none_on_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "debian").mkdir()
    (tmp_path / "debian" / "changelog").write_text(_OLD)

    def boom(self, *args, **kwargs):
        raise OSError("nope")

    monkeypatch.setattr(Path, "read_text", boom)
    writer = DebianChangelogWriter(type="debian-changelog")
    assert DebianChangelogImpl().read_version(writer, tmp_path) is None


def test_write_promote_drops_prerelease_stanzas(tmp_path: Path):
    (tmp_path / "multicz.toml").write_text(_CONFIG)
    config = load_config(tmp_path / "multicz.toml")
    (tmp_path / "debian").mkdir()
    changelog = tmp_path / "debian" / "changelog"
    changelog.write_text(_OLD)
    writer = config.components["mypkg"].writers[0]
    ctx = WriteContext(
        repo=tmp_path,
        component_name="mypkg",
        component=config.components["mypkg"],
        writer=writer,
        planned=None,  # type: ignore[arg-type]
        new_version="1.0.0",
        config=config,
        relevant_commits=[],
        is_finalize=True,
    )
    DebianChangelogImpl().write(ctx)
    text = changelog.read_text()
    assert "mypkg (1.0.0-1)" in text
    assert "1.0.0~rc1" not in text


def test_validate_ignores_foreign_writer(tmp_path: Path):
    impl = DebianChangelogImpl()
    assert list(impl.validate(_NotADebianWriter(), tmp_path)) == []  # type: ignore[arg-type]


def test_validate_unreadable_changelog_is_error(tmp_path: Path):
    (tmp_path / "debian" / "changelog").mkdir(parents=True)
    writer = DebianChangelogWriter(type="debian-changelog")
    findings = list(DebianChangelogImpl().validate(writer, tmp_path))
    assert [f.check for f in findings] == ["debian_changelog_unreadable"]
    assert findings[0].level == "error"


def test_maintainer_from_debian_control(tmp_path: Path):
    (tmp_path / "debian").mkdir()
    (tmp_path / "debian" / "control").write_text("Source: x\nMaintainer: Ctl <ctl@example.com>\n")
    assert dc._resolve_maintainer(tmp_path, None) == "Ctl <ctl@example.com>"


def test_maintainer_placeholder_without_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    assert dc._resolve_maintainer(tmp_path, None) == "Unknown <unknown@example.com>"
