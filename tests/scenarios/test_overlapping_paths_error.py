"""Scenario: two components claiming the same files.

The default ``overlap_policy = "error"`` should refuse to plan
(via ``multicz validate``) until the user clarifies. ``first-match``
emits a warning, ``allow`` is silent, ``all`` bumps every claiming
component. This scenario locks the default in place.
"""

from __future__ import annotations

import json

from multicz.cli import app

OVERLAP_CONFIG = """\
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[components.lib]
paths = ["src/**"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
"""


def test_default_overlap_policy_is_error(make_repo, runner):
    make_repo({
        "multicz.toml": OVERLAP_CONFIG,
        "pyproject.toml": '[project]\nname = "x"\nversion = "1.0.0"\n',
        "src/main.py": "x = 1\n",
    })

    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "path_overlap" in result.output


def test_overlap_policy_all_bumps_both_components(
    make_repo, commit, runner
):
    make_repo({
        "multicz.toml": '[project]\noverlap_policy = "all"\n' + OVERLAP_CONFIG,
        "pyproject.toml": '[project]\nname = "x"\nversion = "1.0.0"\n',
        "src/main.py": "x = 1\n",
    })
    commit({"src/main.py": "x = 2\n"}, "feat: shared change")

    result = runner.invoke(app, ["plan", "--output", "json"])
    payload = json.loads(result.stdout)
    assert "api" in payload["bumps"]
    assert "lib" in payload["bumps"]
