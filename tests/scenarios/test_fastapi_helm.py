# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Scenario: FastAPI service shipped with a Helm chart.

The reference layout from `examples/fastapi-helm/`. A single feat
commit on the API code should:

  - bump api as minor (feat)
  - mirror the new api version into Chart.yaml:appVersion
  - cascade a patch on the chart so the new appVersion is pinned
    inside a fresh chart version
"""

from __future__ import annotations

import json

from multicz.cli import app

CONFIG = """\
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]
changelog = "CHANGELOG.md"

[components.chart]
paths = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
changelog = "charts/myapp/CHANGELOG.md"
"""


def test_feat_on_api_bumps_minor_and_cascades_patch_on_chart(
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
    commit({"src/main.py": "x = 2\n"}, "feat(api): add login")

    result = runner.invoke(app, ["plan", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)

    api = payload["bumps"]["api"]
    assert api["next_version"] == "1.3.0"
    assert api["kind"] == "minor"

    chart = payload["bumps"]["chart"]
    assert chart["next_version"] == "0.4.1"
    assert chart["kind"] == "patch"
    assert any(r["kind"] == "mirror" for r in chart["reasons"])


def test_chart_template_only_change_does_not_bump_api(
    make_repo, commit, runner
):
    """A change confined to charts/myapp/templates/ must NOT touch api."""
    make_repo({
        "multicz.toml": CONFIG,
        "pyproject.toml": '[project]\nname = "x"\nversion = "1.2.0"\n',
        "src/main.py": "x = 1\n",
        "charts/myapp/Chart.yaml": (
            "apiVersion: v2\nname: x\nversion: 0.4.0\nappVersion: 1.2.0\n"
        ),
        "charts/myapp/templates/deployment.yaml": "kind: Deployment\n",
    })
    commit(
        {"charts/myapp/templates/deployment.yaml": "kind: Deployment\nx: 1\n"},
        "fix(chart): tweak deployment",
    )

    result = runner.invoke(app, ["plan", "--output", "json"])
    payload = json.loads(result.stdout)
    assert "api" not in payload["bumps"]
    assert payload["bumps"]["chart"]["kind"] == "patch"
