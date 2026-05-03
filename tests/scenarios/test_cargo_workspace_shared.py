# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Scenario: Cargo workspace with a shared `[workspace.package].version`.

When the workspace shares a single version across all members, multicz
collapses it into ONE component. Member crates inheriting via
``version.workspace = true`` must NOT appear as independent components,
otherwise a single semver bump would write the same version twice.
"""

from __future__ import annotations

import json

from multicz.cli import app

ROOT_CARGO = """\
[package]
name = "rootkit"
version = "0.1.0"

[workspace]
members = ["crates/foo", "crates/bar"]

[workspace.package]
version = "0.1.0"
"""

CONFIG = """\
[components.rootkit]
paths = ["src/**", "Cargo.toml", "crates/**"]
bump_files = [{ file = "Cargo.toml", key = "workspace.package.version" }]
"""


def test_feat_on_inheriting_member_bumps_the_shared_version(
    make_repo, commit, runner
):
    make_repo({
        "multicz.toml": CONFIG,
        "Cargo.toml": ROOT_CARGO,
        "src/lib.rs": "// root crate\n",
        "crates/foo/Cargo.toml": (
            '[package]\nname = "foo"\nversion.workspace = true\n'
        ),
        "crates/foo/src/lib.rs": "// foo\n",
        "crates/bar/Cargo.toml": (
            '[package]\nname = "bar"\nversion.workspace = true\n'
        ),
        "crates/bar/src/lib.rs": "// bar\n",
    })
    commit({"crates/foo/src/lib.rs": "// foo!\n"}, "feat: foo gains a feature")

    result = runner.invoke(app, ["plan", "--output", "json"])
    payload = json.loads(result.stdout)

    assert "foo" not in payload["bumps"]
    assert "bar" not in payload["bumps"]
    assert payload["bumps"]["rootkit"]["next_version"] == "0.2.0"
