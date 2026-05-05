# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Unit tests for individual discovery strategies and relations.

End-to-end coverage of ``discover_components`` lives in
``test_discovery.py`` — it exercises the whole orchestration pipeline.
This file zooms in on each strategy / relation in isolation: instantiate
it, hand it a tmp_path containing only the manifests it cares about,
and assert on its yielded ``DiscoveryResult`` (or post-pass mutation)
without going through the orchestrator.
"""

from pathlib import Path

from multicz.config import Component, FileKey
from multicz.discovery.cargo import CargoDiscovery
from multicz.discovery.context import DiscoveryContext, DiscoveryResult
from multicz.discovery.go import GoDiscovery
from multicz.discovery.gradle import GradleDiscovery
from multicz.discovery.helm import HelmDiscovery
from multicz.discovery.python import PythonDiscovery
from multicz.discovery.relations import (
    PythonHelmAppVersionRelation,
)


def _ctx(repo: Path) -> DiscoveryContext:
    return DiscoveryContext(repo=repo)


# PythonDiscovery ----------------------------------------------------------


def test_python_strategy_yields_root_component(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\nversion = "1.0.0"\n'
    )
    (tmp_path / "src").mkdir()
    results = list(PythonDiscovery().discover(tmp_path, _ctx(tmp_path)))
    assert len(results) == 1
    r = results[0]
    assert r.raw_name == "myapp"
    assert r.kind == "python"
    assert r.suffix == "py"
    assert "src/**" in r.component.paths
    assert "pyproject.toml" in r.component.paths


def test_python_strategy_yields_each_workspace_member(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
    )
    for name in ("api", "cli"):
        member = tmp_path / "packages" / name
        member.mkdir(parents=True)
        (member / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
        )
    results = list(PythonDiscovery().discover(tmp_path, _ctx(tmp_path)))
    names = {r.raw_name for r in results}
    assert names == {"api", "cli"}


def test_python_strategy_skips_pyproject_without_project_table(tmp_path: Path) -> None:
    """A workspace orchestrator with no `[project]` table is not a
    component itself."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n'
    )
    results = list(PythonDiscovery().discover(tmp_path, _ctx(tmp_path)))
    assert results == []


# CargoDiscovery -----------------------------------------------------------


def test_cargo_strategy_yields_single_crate(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "mycrate"\nversion = "0.1.0"\n'
    )
    results = list(CargoDiscovery().discover(tmp_path, _ctx(tmp_path)))
    assert len(results) == 1
    assert results[0].raw_name == "mycrate"
    assert results[0].kind == "cargo"
    # Cargo always ships src/** unconditionally (even if the dir doesn't exist).
    assert "src/**" in results[0].component.paths


# HelmDiscovery ------------------------------------------------------------


def test_helm_strategy_yields_one_per_chart(tmp_path: Path) -> None:
    for dirname in ("api", "worker"):
        chart = tmp_path / "charts" / dirname
        chart.mkdir(parents=True)
        (chart / "Chart.yaml").write_text(
            f"apiVersion: v2\nname: {dirname}\nversion: 0.1.0\n"
        )
    results = list(HelmDiscovery().discover(tmp_path, _ctx(tmp_path)))
    assert {r.raw_name for r in results} == {"api", "worker"}
    assert all(r.kind == "helm" for r in results)


# GoDiscovery --------------------------------------------------------------


def test_go_strategy_yields_module(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module github.com/acme/svc\n")
    results = list(GoDiscovery().discover(tmp_path, _ctx(tmp_path)))
    assert len(results) == 1
    assert results[0].raw_name == "svc"
    assert results[0].kind == "go"
    # Go is tag-driven — no bump_files.
    assert results[0].component.bump_files == []


# GradleDiscovery ----------------------------------------------------------


def test_gradle_strategy_skips_property_file_without_version(tmp_path: Path) -> None:
    (tmp_path / "gradle.properties").write_text("foo=bar\n")
    results = list(GradleDiscovery().discover(tmp_path, _ctx(tmp_path)))
    assert results == []


# Relations ----------------------------------------------------------------


def _result(name: str, kind, suffix: str, comp: Component) -> DiscoveryResult:
    return DiscoveryResult(raw_name=name, kind=kind, suffix=suffix, component=comp)


def test_relation_pairs_lone_python_with_lone_chart(tmp_path: Path) -> None:
    """The unambiguous case: one python + one chart, regardless of name."""
    py = Component(
        paths=["src/**", "pyproject.toml"],
        bump_files=[FileKey(file=Path("pyproject.toml"), key="project.version")],
    )
    chart = Component(
        paths=["charts/myapp/**"],
        bump_files=[FileKey(file=Path("charts/myapp/Chart.yaml"), key="version")],
    )
    components = {"api": py, "myapp": chart}
    context = _ctx(tmp_path)
    context.register("api", _result("api", "python", "py", py))
    context.register("myapp", _result("myapp", "helm", "chart", chart))

    PythonHelmAppVersionRelation().link(tmp_path, components, context)

    assert len(py.mirrors) == 1
    mirror = py.mirrors[0]
    assert str(mirror.file) == "charts/myapp/Chart.yaml"
    assert mirror.key == "appVersion"


def test_relation_pairs_only_matching_names_when_many(tmp_path: Path) -> None:
    """Multi-python multi-chart: only same-name pairs get wired."""
    py_api = Component(
        paths=["packages/api/**"],
        bump_files=[FileKey(file=Path("packages/api/pyproject.toml"), key="project.version")],
    )
    py_worker = Component(
        paths=["packages/worker/**"],
        bump_files=[FileKey(file=Path("packages/worker/pyproject.toml"), key="project.version")],
    )
    chart_api = Component(
        paths=["charts/api/**"],
        bump_files=[FileKey(file=Path("charts/api/Chart.yaml"), key="version")],
    )
    components = {"api": py_api, "worker": py_worker, "api-chart": chart_api}
    context = _ctx(tmp_path)
    context.register("api", _result("api", "python", "py", py_api))
    context.register("worker", _result("worker", "python", "py", py_worker))
    context.register("api-chart", _result("api", "helm", "chart", chart_api))

    PythonHelmAppVersionRelation().link(tmp_path, components, context)

    # api gets the mirror (raw_name match), worker does not.
    assert len(py_api.mirrors) == 1
    assert str(py_api.mirrors[0].file) == "charts/api/Chart.yaml"
    assert py_worker.mirrors == []


def test_relation_no_op_when_either_kind_missing(tmp_path: Path) -> None:
    py = Component(
        paths=["src/**"],
        bump_files=[FileKey(file=Path("pyproject.toml"), key="project.version")],
    )
    components = {"api": py}
    context = _ctx(tmp_path)
    context.register("api", _result("api", "python", "py", py))
    PythonHelmAppVersionRelation().link(tmp_path, components, context)
    assert py.mirrors == []
