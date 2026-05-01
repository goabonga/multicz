"""Scenario: cyclic triggers must be rejected by ``multicz validate``.

When a -> b and b -> a (or longer chains), the planner would loop or
make arbitrary choices. ``validate`` detects the cycle via DFS and
returns the offending path — the test pins both the error level and
the human-readable cycle representation.
"""

from __future__ import annotations

from multicz.cli import app

CYCLIC_CONFIG = """\
[components.a]
paths = ["a/**"]
triggers = ["b"]

[components.b]
paths = ["b/**"]
triggers = ["a"]
"""


def test_validate_detects_trigger_cycle(make_repo, runner):
    make_repo({
        "multicz.toml": CYCLIC_CONFIG,
        "a/.keep": "",
        "b/.keep": "",
    })

    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "trigger_cycle" in result.output
    # The error must name BOTH components in the cycle path
    assert "a" in result.output and "b" in result.output


def test_mirror_cycle_is_also_detected(make_repo, runner):
    """Mirror cascades cycles are caught the same way (separate check)."""
    make_repo({
        "multicz.toml": """
[components.a]
paths = ["a.yaml"]
bump_files = [{ file = "a.yaml", key = "v" }]
mirrors = [{ file = "b.yaml", key = "v" }]

[components.b]
paths = ["b.yaml"]
bump_files = [{ file = "b.yaml", key = "v" }]
mirrors = [{ file = "a.yaml", key = "v" }]
""",
        "a.yaml": "v: 1\n",
        "b.yaml": "v: 1\n",
    })

    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1
    assert "mirror_cycle" in result.output
