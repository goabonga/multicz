# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Cover Node discovery error handling, workspace exclusions and name clashes."""

from pathlib import Path

from multicz.config import Component
from multicz.discovery._common import _NOISE_DIRS
from multicz.discovery.context import DiscoveryContext
from multicz.discovery.node import (
    _detect_node,
    _node_unique,
    _read_package_json_name,
    _read_package_json_version,
    _read_workspace_globs,
)


def test_name_and_version_of_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "package.json"
    path.write_text("{not json")
    assert _read_package_json_name(path) is None
    assert _read_package_json_version(path) is None


def test_workspace_globs_fall_back_to_pnpm_on_invalid_package_json(tmp_path: Path) -> None:
    pkg = tmp_path / "package.json"
    pkg.write_text("{not json")
    pnpm = tmp_path / "pnpm-workspace.yaml"
    pnpm.write_text("packages:\n  - 'pkgs/*'\n")
    assert _read_workspace_globs(pkg, pnpm) == ["pkgs/*"]


def test_workspace_globs_invalid_pnpm_yaml(tmp_path: Path) -> None:
    pnpm = tmp_path / "pnpm-workspace.yaml"
    pnpm.write_text("packages: [unclosed\n")
    assert _read_workspace_globs(tmp_path / "package.json", pnpm) == []


def test_workspace_member_in_noise_dir_is_skipped(tmp_path: Path) -> None:
    noise = sorted(_NOISE_DIRS)[0]
    (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')
    for dirname in ("ok", noise):
        member = tmp_path / "packages" / dirname
        member.mkdir(parents=True)
        (member / "package.json").write_text(f'{{"name": "{dirname}", "version": "1.0.0"}}')
    components: dict[str, Component] = {}
    _detect_node(tmp_path, components, DiscoveryContext(repo=tmp_path))
    assert set(components) == {"ok"}


def test_only_exclusions_adds_nothing(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name": "root", "workspaces": ["!packages/x"]}')
    components: dict[str, Component] = {}
    _detect_node(tmp_path, components, DiscoveryContext(repo=tmp_path))
    assert components == {}


def test_root_package_claims_src_when_no_python(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name": "web", "version": "1.0.0"}')
    (tmp_path / "src").mkdir()
    components: dict[str, Component] = {}
    _detect_node(tmp_path, components, DiscoveryContext(repo=tmp_path))
    assert components["web"].paths == ["src/**", "package.json"]


def test_node_unique_counts_past_taken_suffix() -> None:
    assert _node_unique("app", set()) == "app"
    assert _node_unique("app", {"app"}) == "app-js"
    assert _node_unique("app", {"app", "app-js"}) == "app-js-2"
    assert _node_unique("app", {"app", "app-js", "app-js-2"}) == "app-js-3"
