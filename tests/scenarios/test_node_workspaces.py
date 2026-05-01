"""Scenario: npm workspaces (the JS monorepo case).

Root package.json declares ``"workspaces": ["packages/*"]``. Each
member has its own version. A `feat` on one workspace member must
bump only that member.
"""

from __future__ import annotations

import json

from multicz.cli import app

CONFIG = """\
[components.web]
paths = ["packages/web/**"]
bump_files = [{ file = "packages/web/package.json", key = "version" }]

[components.shared]
paths = ["packages/shared/**"]
bump_files = [{ file = "packages/shared/package.json", key = "version" }]
"""


def test_feat_on_one_workspace_member_does_not_touch_the_other(
    make_repo, commit, runner
):
    make_repo({
        "multicz.toml": CONFIG,
        "package.json": '{"name": "monorepo", "private": true, '
                         '"workspaces": ["packages/*"]}\n',
        "packages/web/package.json": '{"name": "web", "version": "1.0.0"}\n',
        "packages/web/src/index.tsx": "console.log(1);\n",
        "packages/shared/package.json": '{"name": "shared", "version": "0.5.0"}\n',
        "packages/shared/src/utils.ts": "export const x = 1;\n",
    })
    commit(
        {"packages/web/src/index.tsx": "console.log(2);\n"},
        "feat(web): redesign nav",
    )

    result = runner.invoke(app, ["plan", "--output", "json"])
    payload = json.loads(result.stdout)

    assert payload["bumps"]["web"]["next_version"] == "1.1.0"
    assert "shared" not in payload["bumps"]


def test_npm_workspace_bang_pattern_excludes_member(
    make_repo, commit, runner
):
    """`!packages/legacy` in the workspaces array drops the legacy member."""
    make_repo({
        "multicz.toml": """
[components.keep]
paths = ["packages/keep/**"]
bump_files = [{ file = "packages/keep/package.json", key = "version" }]
""",
        "package.json": '{"name": "monorepo", '
                         '"workspaces": ["packages/*", "!packages/legacy"]}\n',
        "packages/keep/package.json": '{"name": "keep", "version": "1.0.0"}\n',
        "packages/keep/src/index.ts": "export const a = 1;\n",
        "packages/legacy/package.json": '{"name": "legacy", "version": "0.1.0"}\n',
        "packages/legacy/src/index.ts": "export const a = 1;\n",
    })
    # Touch BOTH packages — only `keep` should appear in the plan.
    commit(
        {
            "packages/keep/src/index.ts": "export const a = 2;\n",
            "packages/legacy/src/index.ts": "export const a = 2;\n",
        },
        "feat: shared change",
    )

    result = runner.invoke(app, ["plan", "--output", "json"])
    payload = json.loads(result.stdout)
    assert "keep" in payload["bumps"]
    assert "legacy" not in payload["bumps"]
