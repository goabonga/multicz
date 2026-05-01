"""Scenario: uv workspace at the root, two service packages as members.

The root pyproject declares ``[tool.uv.workspace]``. Each member has
its own ``[project].version``. A change inside one member must:

  - bump only that member, not the other
  - not bump the root (orchestrator-only when no [project] block)
"""

from __future__ import annotations

import json

from multicz.cli import app

ROOT_PYPROJECT = """\
[tool.uv.workspace]
members = ["services/*"]
"""

CONFIG = """\
[components.api]
paths = ["services/api/**"]
bump_files = [{ file = "services/api/pyproject.toml", key = "project.version" }]

[components.worker]
paths = ["services/worker/**"]
bump_files = [{ file = "services/worker/pyproject.toml", key = "project.version" }]
"""


def test_feat_on_api_member_does_not_touch_worker(make_repo, commit, runner):
    make_repo({
        "multicz.toml": CONFIG,
        "pyproject.toml": ROOT_PYPROJECT,
        "services/api/pyproject.toml": (
            '[project]\nname = "api"\nversion = "1.0.0"\n'
        ),
        "services/api/src/main.py": "x = 1\n",
        "services/worker/pyproject.toml": (
            '[project]\nname = "worker"\nversion = "0.5.0"\n'
        ),
        "services/worker/src/main.py": "x = 1\n",
    })
    commit({"services/api/src/main.py": "x = 2\n"}, "feat(api): new endpoint")

    result = runner.invoke(app, ["plan", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)

    assert payload["bumps"]["api"]["next_version"] == "1.1.0"
    assert "worker" not in payload["bumps"]


def test_independent_members_bump_independently(make_repo, commit, runner):
    """Two members can bump simultaneously when both are touched."""
    make_repo({
        "multicz.toml": CONFIG,
        "pyproject.toml": ROOT_PYPROJECT,
        "services/api/pyproject.toml": (
            '[project]\nname = "api"\nversion = "1.0.0"\n'
        ),
        "services/api/src/main.py": "x = 1\n",
        "services/worker/pyproject.toml": (
            '[project]\nname = "worker"\nversion = "0.5.0"\n'
        ),
        "services/worker/src/main.py": "x = 1\n",
    })
    commit({"services/api/src/main.py": "x = 2\n"}, "feat: api change")
    commit({"services/worker/src/main.py": "x = 2\n"}, "fix: worker bug")

    result = runner.invoke(app, ["plan", "--output", "json"])
    payload = json.loads(result.stdout)

    assert payload["bumps"]["api"]["next_version"] == "1.1.0"
    assert payload["bumps"]["api"]["kind"] == "minor"
    assert payload["bumps"]["worker"]["next_version"] == "0.5.1"
    assert payload["bumps"]["worker"]["kind"] == "patch"
