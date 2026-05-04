# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>

"""Scenario: mirror cascade with per-mirror changelog customization.

Reproduces the multicz-python-docker-helm pattern: two upstream mirrors
both target the same downstream component (the umbrella chart), each
with its own ``changelog_section`` and ``changelog_format``. The
downstream CHANGELOG.md must:

  - group both cascade lines under the shared custom section
    (``Subchart updates``), not under the default ``Dependencies``
  - render each mirror's custom phrase verbatim with its own upstream
    version
  - omit the default ``Dependencies`` section entirely

A separate component routes its mirror line into an existing
commit-driven section (``Features``) to verify the merge path:
the cascade line lands at the bottom of the existing section instead of
creating a parallel one.
"""

from __future__ import annotations

from multicz.cli import app

CONFIG = """\
[components.api]
paths = ["src/api/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
changelog = "CHANGELOG.md"

[[components.api.mirrors]]
file = "charts/myapp-api/Chart.yaml"
key = "appVersion"
changelog_section = "Features"
changelog_format = "Sync chart-api appVersion to {upstream_version}"

[components.chart-api]
paths = ["charts/myapp-api/**"]
bump_files = [{ file = "charts/myapp-api/Chart.yaml", key = "version" }]
changelog = "charts/myapp-api/CHANGELOG.md"

[[components.chart-api.mirrors]]
file = "charts/myapp/Chart.yaml"
key = "regex:- name: myapp-api\\\\s+version:\\\\s+(\\\\S+)"
changelog_section = "Subchart updates"
changelog_format = "Bump `myapp-api` dependency to `{upstream_version}`"

[components.chart-web]
paths = ["charts/myapp-web/**"]
bump_files = [{ file = "charts/myapp-web/Chart.yaml", key = "version" }]
changelog = "charts/myapp-web/CHANGELOG.md"

[[components.chart-web.mirrors]]
file = "charts/myapp/Chart.yaml"
key = "regex:- name: myapp-web\\\\s+version:\\\\s+(\\\\S+)"
changelog_section = "Subchart updates"
changelog_format = "Bump `myapp-web` dependency to `{upstream_version}`"

[components.chart]
paths = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
changelog = "charts/myapp/CHANGELOG.md"
"""


CHART_YAML = """\
apiVersion: v2
name: myapp
version: 0.4.0
dependencies:
  - name: myapp-api
    version: 0.4.0
  - name: myapp-web
    version: 0.4.0
"""


def _seed():
    return {
        "multicz.toml": CONFIG,
        "pyproject.toml": '[project]\nname = "x"\nversion = "1.2.0"\n',
        "src/api/main.py": "x = 1\n",
        "charts/myapp-api/Chart.yaml": (
            "apiVersion: v2\nname: myapp-api\nversion: 0.4.0\n"
            "appVersion: 1.2.0\n"
        ),
        "charts/myapp-web/Chart.yaml": (
            "apiVersion: v2\nname: myapp-web\nversion: 0.4.0\n"
            "appVersion: 1.0.0\n"
        ),
        "charts/myapp/Chart.yaml": CHART_YAML,
    }


def test_api_to_chart_api_uses_custom_format_in_features_section(
    make_repo, commit, runner
):
    """The api -> chart-api mirror routes its cascade line into the
    chart-api CHANGELOG's ``Features`` section (matching an existing
    commit-driven section title) with the custom format."""
    repo = make_repo(_seed())
    commit({"src/api/main.py": "x = 2\n"}, "feat: change")

    runner.invoke(app, ["bump", "--commit", "--tag"])

    body = (repo / "charts/myapp-api/CHANGELOG.md").read_text()
    assert "### Features" in body
    assert "Sync chart-api appVersion to 1.3.0" in body
    # No default Dependencies section.
    assert "### Dependencies" not in body
    assert "Track `api`" not in body


def test_subchart_mirrors_share_custom_section_in_umbrella_changelog(
    make_repo, commit, runner
):
    """Both chart-api and chart-web mirror writes into the umbrella
    ``charts/myapp/Chart.yaml`` cascade onto ``chart``. Their cascade
    lines must group under one shared ``Subchart updates`` H3 in the
    umbrella's CHANGELOG.md, with each mirror's custom format applied."""
    repo = make_repo(_seed())
    # Touch both subcharts so chart-api and chart-web each bump,
    # and each cascades its mirror into chart.
    commit({"charts/myapp-api/templates/foo.yaml": "kind: ConfigMap\n"},
           "feat(chart-api): add cm")
    commit({"charts/myapp-web/templates/bar.yaml": "kind: ConfigMap\n"},
           "feat(chart-web): add cm")

    runner.invoke(app, ["bump", "--commit", "--tag"])

    body = (repo / "charts/myapp/CHANGELOG.md").read_text()

    # Custom section appears exactly once — both lines under one H3.
    assert body.count("### Subchart updates") == 1

    # Both custom-formatted cascade lines present.
    assert "Bump `myapp-api` dependency to" in body
    assert "Bump `myapp-web` dependency to" in body

    # Default cascade section did NOT render (everything routed away).
    assert "### Dependencies" not in body
    assert "Track `chart-api`" not in body
    assert "Track `chart-web`" not in body
