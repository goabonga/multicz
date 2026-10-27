# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""``multicz graph``: rooted views, several roots, cycle guards, bad input."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from multicz.cli import app
from multicz.cli.commands.graph import _reachable, _render_tree, _walk_tree

CONFIG = """
[components.api]
paths = ["api/**"]
bump_files = [{ file = "api/v.toml", key = "version" }]

[components.web]
paths = ["web/**"]
depends_on = ["api"]
bump_files = [{ file = "web/v.toml", key = "version" }]

[components.docs]
paths = ["docs/**"]
bump_files = [{ file = "docs/v.toml", key = "version" }]
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    files = {"multicz.toml": CONFIG}
    for name in ("api", "web", "docs"):
        files[f"{name}/v.toml"] = 'version = "1.0.0"\n'
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "chore: init")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_tree_with_several_roots(repo: Path):
    result = CliRunner().invoke(app, ["graph"])
    assert result.exit_code == 0, result.output
    assert "api" in result.output
    assert "docs" in result.output
    assert "web" in result.output


def test_mermaid_restricted_to_a_component(repo: Path):
    result = CliRunner().invoke(app, ["graph", "-o", "mermaid", "-c", "api"])
    assert result.exit_code == 0, result.output
    assert "  api -->|depends_on| web" in result.output
    assert "  docs" not in result.output


def test_dot_restricted_to_a_component(repo: Path):
    result = CliRunner().invoke(app, ["graph", "-o", "dot", "-c", "api"])
    assert result.exit_code == 0, result.output
    assert '"api" -> "web"' in result.output
    assert '"docs"' not in result.output


def test_unknown_output_format(repo: Path):
    result = CliRunner().invoke(app, ["graph", "-o", "svg"])
    assert result.exit_code == 1
    assert "unknown --output" in result.output


def test_unknown_component(repo: Path):
    result = CliRunner().invoke(app, ["graph", "-c", "nope"])
    assert result.exit_code == 1
    assert "unknown component" in result.output


def test_walk_tree_marks_cycles():
    from rich.tree import Tree

    tree = Tree("a")
    children = {"a": [("b", "depends_on")], "b": [("a", "depends_on")]}
    _walk_tree(tree, "a", children, frozenset())
    b_node = tree.children[0]
    a_again = b_node.children[0]
    assert "cycle back to a" in str(a_again.children[0].label)


def test_render_tree_pure_cycle_falls_back_to_all_components(capsys: pytest.CaptureFixture[str]):
    config = SimpleNamespace(components={"a": object(), "b": object()})
    edges = [("a", "b", "depends_on"), ("b", "a", "depends_on")]
    _render_tree(config, edges, root=None)
    out = capsys.readouterr().out
    assert "cycle back to" in out


def test_reachable_visits_shared_descendants_once():
    edges = [("a", "b", "x"), ("a", "c", "x"), ("b", "d", "x"), ("c", "d", "x")]
    assert _reachable("a", edges) == {"a", "b", "c", "d"}
