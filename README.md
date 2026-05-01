# multicz

Multi-component versioning for monorepos. Bump a Python app, its Docker image,
and the Helm chart that deploys it from a single conventional-commit history —
each with its own version line and its own git tag.

## The problem

You have one repo with a few moving parts:

```
repo/
├── src/                 # FastAPI app
├── pyproject.toml       # → version 1.2.0
├── Dockerfile           # built and tagged from the app version
└── charts/myapp/
    ├── Chart.yaml       # version: 0.4.0 / appVersion: 1.2.0
    └── templates/       # kubernetes manifests
```

A change to `src/` is a new app release; a change only under
`charts/myapp/templates/` is a new chart release for the *same* app.
Standard tools bump everything together or force you to script per-folder
logic. `multicz` makes the rule explicit in `multicz.toml`.

## Install

```sh
uv add --dev multicz   # or: pip install multicz
```

## Quickstart

```sh
multicz init           # writes a starter multicz.toml
$EDITOR multicz.toml   # declare your components
multicz status         # show which components would bump and why
multicz bump --dry-run # plan the bump without touching files
multicz bump           # apply the plan
```

## How it works

Each component declares:

* `paths` — gitignore-style globs of files it owns;
* `bump_files` — where the canonical version is written;
* `mirrors` — files that should reflect this component's version (e.g. a
  Helm chart's `appVersion` mirroring the app version);
* `triggers` — other components whose bumps should trigger this one;
* `changelog` — path to a `CHANGELOG.md` the planner should keep in sync.

The planner runs three passes:

1. **direct** — for every component, look at conventional commits since its
   last tag whose changed files map to it; pick the strongest implied bump
   (`feat` → minor, `fix`/`perf` → patch, `!`/`BREAKING CHANGE` → major).
2. **triggers** — propagate bumps along declared upstream edges.
3. **mirror cascade** — when a component A writes its version into a file
   owned by component B, B receives a patch bump. This keeps Helm chart
   immutability: `chart-0.5.0` always pins the same `appVersion`.

## Example: FastAPI + Helm chart

```toml
[components.api]
paths = ["src/**", "pyproject.toml", "tests/**", "Dockerfile"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors    = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]
changelog  = "CHANGELOG.md"

[components.chart]
paths      = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
changelog  = "charts/myapp/CHANGELOG.md"
```

Behavior:

| change | api | image tag | chart.version | appVersion |
|---|---|---|---|---|
| `src/main.py` (feat) | minor | follows api | patch (cascade) | mirror |
| `Dockerfile` (CVE base) | patch | follows api | patch (cascade) | mirror |
| `charts/myapp/templates/dep.yaml` | — | — | patch | — |
| `charts/myapp/values.yaml` (config) | — | — | patch | — |

The Docker image tag is `api.version` itself — read it from CI:

```sh
TAG=$(multicz get api)
docker build -t registry/myapp:$TAG .
docker push registry/myapp:$TAG
helm package charts/myapp
```

## CLI

| command | what it does |
|---|---|
| `multicz init` | write a starter `multicz.toml` |
| `multicz status` | print pending bumps with reasons |
| `multicz bump` | apply bumps to all configured files |
| `multicz bump --dry-run` | plan without writing |
| `multicz bump --commit --tag` | release in one shot: write, commit, tag |
| `multicz bump --commit --tag --push` | …and push commit + tags with `--follow-tags` |
| `multicz bump --output json` | emit `{"bumps": {...}, "git": {...}}` for CI |
| `multicz get <component>` | read the current version from the primary bump file |
| `multicz changelog [-c name]` | per-component conventional-commit log since the last tag |
| `multicz changelog --output md` | the same, grouped into Breaking / Features / Fixes / Perf / Other |
| `multicz bump --no-changelog` | bump versions without touching declared `CHANGELOG.md` files |
| `multicz check <file>` | validate a commit message — wire as a `commit-msg` hook |

### Per-component CHANGELOG.md

When a component declares `changelog = "path/to/CHANGELOG.md"`, every
`multicz bump` automatically prepends a new keep-a-changelog section to
that file:

```markdown
## [1.3.0] - 2026-04-30

### Features

- **api**: add login (`abc1234`)

### Fixes

- null token (`def5678`)
```

The file is created with a small preamble on first use, and subsequent
runs insert the new section directly above the latest existing release.
Pass `--no-changelog` to opt out for a single bump.

#### Configuring sections

By default, only `feat`, `fix`, and `perf` are rendered (under "Features",
"Fixes", "Performance"). Anything else (`chore`, `docs`, `test`, `style`,
`ci`, `build`, `refactor`, `revert`) is silently dropped to keep the
changelog focused on user-visible changes.

To pick your own vocabulary — for example keep-a-changelog's
Added/Changed/Fixed — declare sections in `[project]`:

```toml
[project]
breaking_section_title = "Breaking changes"   # set to "" to disable the bucket
other_section_title = ""                       # set to e.g. "Misc" to keep unmatched

[[project.changelog_sections]]
title = "Added"
types = ["feat"]

[[project.changelog_sections]]
title = "Fixed"
types = ["fix"]

[[project.changelog_sections]]
title = "Changed"
types = ["refactor", "perf"]
```

Sections render in declaration order, after the implicit "Breaking changes"
bucket (if any commit has `!` or a `BREAKING CHANGE:` footer). One commit
type can appear in multiple sections; commits whose type matches no section
are dropped (or land in `other_section_title` if you set it).

### Commit-msg hook

```sh
# .git/hooks/commit-msg
#!/bin/sh
exec multicz check "$1"
```

### One-shot CI release

```yaml
- run: |
    multicz bump --commit --tag --push
    TAG=$(multicz get api)
    docker build -t registry/myapp:$TAG .
    docker push registry/myapp:$TAG
    helm package charts/myapp
```

### Supported file formats

`bump_files` and `mirrors` can point at:

* `.toml` — comments and key order preserved (tomlkit)
* `.yaml` / `.yml` — comments and quote style preserved (ruamel.yaml)
* `.json` — indent and key order preserved (e.g. `package.json`)
* `.properties` — line-based `key=value` substitution (e.g. `gradle.properties`)
* anything else — treated as a one-line `VERSION` file (`key = ` omitted)

### Auto-discovery languages

`multicz init` detects the following manifests across the working tree
and seeds one component per project:

| ecosystem | manifest | name source |
|---|---|---|
| Python | `pyproject.toml` | `[project].name` |
| Helm | `**/Chart.yaml` | `name:` field |
| Rust | `**/Cargo.toml` | `[package].name` (workspaces collapse to one component when `[workspace.package].version` is shared) |
| Go | `**/go.mod` | last segment of `module …` (strips `/vN`) — tag-driven, no version file |
| Gradle | root `gradle.properties` with `version=` | `rootProject.name` from `settings.gradle[.kts]` |
| Node.js | root `package.json` (or workspace members via `workspaces` / `pnpm-workspace.yaml`) | `name` field (npm scopes stripped) |

Common noise dirs (`.git`, `node_modules`, `.venv`, `target`, `build`,
`dist`, `vendor`, …) are excluded from the scan.

## Configuration reference

See [`examples/fastapi-helm/multicz.toml`](examples/fastapi-helm/multicz.toml)
for a fully commented example.

## Why "option A" (mirror cascades chart bump)?

Helm charts are content-addressed by `name-version.tgz`. If `chart-0.5.0`
references `appVersion: 1.2.0` in some pulls and `appVersion: 1.3.0` in
others, you've effectively shipped two different artifacts under the same
name. multicz refuses that: any time the mirrored `appVersion` changes,
the chart version moves with it.

## License

MIT
