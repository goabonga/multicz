---
icon: lucide/rocket
---

# Get started

## Install

```bash
uv add --dev multicz
# or
pip install multicz
```

Verify the install:

```bash
multicz --version
```

## Generate a config

From the repo root:

```bash
multicz init
```

This scans the working tree for `pyproject.toml`, `Chart.yaml`,
`package.json`, `Cargo.toml`, `go.mod`, `gradle.properties`, and
`debian/changelog`, then writes a `multicz.toml` with one component per
detected manifest. See [auto-discovery](concepts.md#auto-discovery) for
the full ruleset.

If the working tree has no detectable manifests, fall back to the generic
stub:

```bash
multicz init --bare
```

To preview without writing:

```bash
multicz init --print            # render to stdout
multicz init --detect           # summary of what would be picked up
multicz init --detect --output json
```

## Minimal config

A single-component repo (Python package):

```toml
[project]
commit_convention = "conventional"
tag_format        = "{component}-v{version}"
initial_version   = "0.1.0"

[components.app]
paths      = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
changelog  = "CHANGELOG.md"
```

A multi-component repo (FastAPI service + Helm chart):

```toml
[components.api]
paths      = ["src/**", "pyproject.toml", "tests/**", "Dockerfile"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors    = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]
changelog  = "CHANGELOG.md"

[components.chart]
paths      = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
changelog  = "charts/myapp/CHANGELOG.md"
```

A change under `src/` bumps `api`, mirrors the new version into
`Chart.yaml:appVersion`, and cascades a patch bump on `chart` so each
released chart pins exactly one app version. See the [FastAPI + Helm
recipe](recipes.md#fastapi-helm) for the full flow.

## First bump

Make sure git history has at least one conventional commit (`feat:`,
`fix:`, `perf:`) since the component's initial tag — or its initial
version if no tags exist yet.

```bash
multicz status              # summary table
multicz plan                # per-component plan with reasons
multicz bump --dry-run      # plan without writing
multicz bump                # apply (no commit, no tag)
```

To release in one shot — write, commit, tag, push:

```bash
multicz bump --commit --tag --push
```

The release commit message follows
[`release_commit_message`](configuration.md#release_commit_message);
the tag scheme follows
[`tag_format`](configuration.md#tag_format) (default
`{component}-v{version}`).

## Inline config

`multicz.toml` always wins, but the config can also live inside an
existing manifest:

=== "pyproject.toml"

    ```toml
    [project]
    name    = "myapp"
    version = "1.0.0"

    [tool.multicz.components.api]
    paths      = ["src/**", "pyproject.toml"]
    bump_files = [{ file = "pyproject.toml", key = "project.version" }]
    ```

=== "package.json"

    ```json
    {
      "name": "monorepo",
      "version": "1.0.0",
      "multicz": {
        "components": [
          { "name": "web", "paths": ["frontend/**"] },
          { "name": "mobile", "paths": ["mobile/**"] }
        ]
      }
    }
    ```

A `pyproject.toml` without `[tool.multicz]` is silently skipped — it's
not treated as the multicz config — so projects that already have a
pyproject for tooling reasons aren't hijacked. See [config
discovery](concepts.md#config-discovery).

## Validate before you release

```bash
multicz validate --strict
```

Catches missing `bump_files`, mirror cycles, path overlaps, and
unparseable changelogs before they botch a release. Wire it as the first
step in CI. See the [validate command](cli.md#validate) and the
[security checklist](security.md#ci-hardening-checklist).

## Commit message hook

Catch non-conventional commits at write time:

```sh
# .git/hooks/commit-msg
#!/bin/sh
exec multicz check "$1"
```

`multicz check` validates a commit message file against the
conventional-commits grammar and is suitable for the `commit-msg` hook.
