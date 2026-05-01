# Scenario tests

End-to-end functional contracts. Each file describes a *user-visible*
shape (a layout, a workflow, a corner case) and asserts what
`multicz` should do against it. They run alongside the unit tests but
serve a different purpose: a regression here means user-visible
behaviour has shifted, even when no individual unit test broke.

| scenario | file |
|---|---|
| FastAPI service + Helm chart with mirror cascade | [`test_fastapi_helm.py`](test_fastapi_helm.py) |
| uv workspace with members | [`test_python_workspace.py`](test_python_workspace.py) |
| npm workspaces (`!pattern` excludes) | [`test_node_workspaces.py`](test_node_workspaces.py) |
| Cargo workspace with `[workspace.package].version` | [`test_cargo_workspace_shared.py`](test_cargo_workspace_shared.py) |
| Debian source package (tilde-form pre-releases) | [`test_debian_package.py`](test_debian_package.py) |
| Overlapping component paths (default `error`) | [`test_overlapping_paths_error.py`](test_overlapping_paths_error.py) |
| Mirror cascade in isolation | [`test_mirror_cascade.py`](test_mirror_cascade.py) |
| Trigger and mirror cycles caught by `validate` | [`test_trigger_cycle_error.py`](test_trigger_cycle_error.py) |

Each scenario is self-contained: it builds a fixture repo, makes
git commits, runs the relevant `multicz` commands, and asserts the
expected output (versions, kind, reasons, exit codes, files written).

Adding a new scenario: drop a `test_<name>.py` next to the others
and use the `make_repo`, `commit`, `git`, and `runner` fixtures from
[`conftest.py`](conftest.py).
