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
* `triggers` — other components whose bumps should trigger this one.

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
paths = ["src/**", "pyproject.toml", "tests/**", "Dockerfile", ".dockerignore"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors    = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]

[components.chart]
paths      = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
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
| `multicz check <file>` | validate a commit message — wire as a `commit-msg` hook |

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
* anything else — treated as a one-line `VERSION` file (`key = ` omitted)

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
