# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Scenario: mirror cascade in isolation.

A single api commit must:

  - bump api (direct, from the commit's bump_kind)
  - cause the chart to bump as patch (mirror cascade — the mirror
    writes into a file owned by the chart, the chart's own version
    therefore needs to move)
  - record both an explicit ``mirror`` reason on the chart and the
    direct commit reason on the api

Two tags must be created in semver-comparable form so the *next*
release can read them back via ``packaging.version.Version``.
"""

from __future__ import annotations

import json

from multicz.cli import app

CONFIG = """\
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]

[components.chart]
paths = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
"""


def test_single_api_commit_cascades_chart_patch(
    make_repo, commit, runner, git
):
    repo = make_repo({
        "multicz.toml": CONFIG,
        "pyproject.toml": '[project]\nname = "x"\nversion = "1.2.0"\n',
        "src/main.py": "x = 1\n",
        "charts/myapp/Chart.yaml": (
            "apiVersion: v2\nname: x\nversion: 0.4.0\nappVersion: 1.2.0\n"
        ),
    })
    commit({"src/main.py": "x = 2\n"}, "feat: change")

    runner.invoke(app, ["bump", "--commit", "--tag"])

    chart_yaml = (repo / "charts/myapp/Chart.yaml").read_text()
    assert "appVersion: 1.3.0" in chart_yaml
    assert "version: 0.4.1" in chart_yaml

    tags = git("tag").split()
    assert "api-v1.3.0" in tags
    assert "chart-v0.4.1" in tags


def test_chart_reasons_attribute_the_cascade_to_api(
    make_repo, commit, runner
):
    make_repo({
        "multicz.toml": CONFIG,
        "pyproject.toml": '[project]\nname = "x"\nversion = "1.2.0"\n',
        "src/main.py": "x = 1\n",
        "charts/myapp/Chart.yaml": (
            "apiVersion: v2\nname: x\nversion: 0.4.0\nappVersion: 1.2.0\n"
        ),
    })
    commit({"src/main.py": "x = 2\n"}, "feat: change")

    result = runner.invoke(app, ["plan", "--output", "json"])
    payload = json.loads(result.stdout)
    chart_reasons = payload["bumps"]["chart"]["reasons"]
    assert any(
        r["kind"] == "mirror" and r["upstream"] == "api"
        for r in chart_reasons
    )
