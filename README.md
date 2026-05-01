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

## Where the config lives

By default, `multicz` looks for a dedicated `multicz.toml` at the repo
root. As a fallback (walked up the directory tree from the cwd), it
also accepts:

- `pyproject.toml` under `[tool.multicz]` — natural for Python projects
- `package.json` under a `"multicz"` key — natural for Node.js projects

Search order at each directory level:

1. `multicz.toml` (always wins when present)
2. `pyproject.toml` *with* a `[tool.multicz]` table
3. `package.json` *with* a `"multicz"` key

A `pyproject.toml` without `[tool.multicz]` is silently skipped — it's
not treated as the multicz config — so projects that already have a
pyproject for tooling reasons aren't hijacked.

Examples:

```toml
# pyproject.toml
[project]
name = "myapp"
version = "1.0.0"

[tool.multicz.components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[tool.multicz.components.web]
paths = ["frontend/**"]
bump_files = [{ file = "frontend/package.json", key = "version" }]
```

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

`multicz init` still writes a dedicated `multicz.toml`. To inline the
config into `pyproject.toml` or `package.json`, copy the body of the
generated `multicz.toml` under the appropriate parent key.

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

Components can be declared in either of two equivalent TOML syntaxes:

```toml
# Dict-of-tables (concise; default emitted by `multicz init`)
[components.api]
paths = ["src/**", "pyproject.toml"]

[components.web]
paths = ["frontend/**"]
```

```toml
# Array-of-tables (preferred when you have many components or want
# to keep declaration order obvious in the file layout)
[[components]]
name = "api"
paths = ["src/**", "pyproject.toml"]

[[components]]
name = "web"
paths = ["frontend/**"]
```

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
| `multicz status` | brief table of pending bumps with reason summaries |
| `multicz plan` | per-component plan with explicit reasons (commit / trigger / mirror) |
| `multicz plan --output json` | machine-readable shape for CI |
| `multicz explain <component>` | full breakdown — every commit, the matched files, every cascade |
| `multicz bump` | apply bumps to all configured files |
| `multicz bump --dry-run` | plan without writing |
| `multicz bump --commit --tag` | release in one shot: write, commit, tag |
| `multicz bump --commit --tag --push` | …and push commit + tags with `--follow-tags` |
| `multicz bump --output json` | emit `{"bumps": {...}, "git": {...}}` for CI |
| `multicz get <component>` | read the current version from the primary bump file |
| `multicz changelog [-c name]` | per-component conventional-commit log since the last tag |
| `multicz changelog --output md` | the same, grouped into Breaking / Features / Fixes / Perf / Other |
| `multicz bump --no-changelog` | bump versions without touching declared `CHANGELOG.md` files |
| `multicz bump --pre rc` | enter / continue a release-candidate cycle (`1.2.3` → `1.3.0-rc.1` → `1.3.0-rc.2`) |
| `multicz bump --finalize` | drop a pre-release suffix (`1.3.0-rc.2` → `1.3.0`) — works with no new commits |
| `multicz check <file>` | validate a commit message — wire as a `commit-msg` hook |
| `multicz validate` | run every config + repo sanity check (CI gate) |
| `multicz validate --strict` | also fail on warnings (overlapping paths, useless mirrors, …) |
| `multicz validate --output json` | machine-readable findings shape |

### Release candidates

A typical RC workflow:

```sh
# starting from api-v1.2.3, with new feat commits on the branch
multicz bump --pre rc --commit --tag      # → api-v1.3.0-rc.1
# more fixes
multicz bump --pre rc --commit --tag      # → api-v1.3.0-rc.2
# QA approves — ship the final
multicz bump --finalize --commit --tag    # → api-v1.3.0
```

`--pre <label>` accepts any label (`rc`, `alpha`, `beta`, `dev`, …) and
the counter resets when you switch labels. `--finalize` is allowed even
when no commits landed since the last RC tag — finalising IS a release
event in its own right. Without either flag, a `multicz bump` from a
pre-release version auto-finalises.

For Debian-format components the changelog stanza renders with `~`
notation so `apt`'s ordering puts pre-releases *before* the final:
`mypkg (1.3.0~rc1-1)` < `mypkg (1.3.0-1)`. The git tag itself stays in
semver form (`mypkg-v1.3.0-rc.1`).

#### Finalize strategy

`[project].finalize_strategy` controls what the changelog looks like
after `--finalize`:

| value | behaviour |
|---|---|
| `consolidate` (default) | the finalize section/stanza lists every commit since the previous *stable* tag, so the new entry contains the cumulative change list. RC sections stay below as history. |
| `promote` | same commit selection as `consolidate`, plus the now-superseded `## [1.3.0-rc.*]` markdown sections (and `mypkg (1.3.0~rc*-*)` Debian stanzas) are removed from the file. The final entry stands alone. |
| `annotate` | the section enumerates only commits since the last *tag* (rc included), so the finalize section may be `_No notable changes._` when no commits landed between the last rc and finalize. Each tag keeps its own dedicated section. |

### `validate`

`multicz validate` is the recommended first step in any CI pipeline —
it surfaces config and repo problems before they cause a botched
release. Each finding has three levels:

| level | examples |
|---|---|
| `error` | a `bump_file` doesn't exist, a trigger cycle, an unparseable `debian/changelog` — the planner can't run safely |
| `warning` | two components claim the same file (`first-match-wins` makes the loser silent), a mirror that loops back to its own component |
| `info` | a mirror to a file no component owns (no cascade fires), a `debian/changelog` that hasn't been created yet |

Exit codes: `0` = clean (warnings/info don't fail), `1` = at least one
error, `2` = `--strict` and at least one warning.

```sh
$ multicz validate
✗ lib: bump_file 'missing.toml' does not exist  (bump_files_exist)
! lib: shares files with 'api' (e.g. 'src/main.py')  (path_overlap)
i api: mirror target 'other.yaml' is not owned by any component  (mirror_target_unowned)
✗ mirror cascade cycle: cycle_a -> cycle_b -> cycle_a  (mirror_cycle)

2 errors, 1 warning, 1 info
```

The check identifier in parentheses (`bump_files_exist`,
`mirror_cycle`, …) is stable so CI logs and PR comments can grep on
it. `--output json` emits the same data as a structured payload with
a counts summary.

### `plan` and `explain`

`multicz plan` is the canonical way to inspect what a release would do
before running it. The text form is grouped per component:

```
api: 1.2.0 → 1.3.0 (minor)
  • abc1234 feat(api): add login flow

chart: 0.4.0 → 0.4.1 (patch)
  • mirror cascade from api (charts/myapp/Chart.yaml:appVersion)
```

`multicz plan --output json` emits a structured payload — exactly what a
CI step needs to gate releases or post a comment on a PR:

```json
{
  "bumps": {
    "api": {
      "current": "1.2.0",
      "next": "1.3.0",
      "kind": "minor",
      "reasons": [
        {
          "kind": "commit",
          "sha": "abc1234...",
          "type": "feat",
          "scope": "api",
          "breaking": false,
          "subject": "add login flow",
          "files": ["src/auth.py", "src/main.py"],
          "bump_kind": "minor"
        }
      ]
    },
    "chart": {
      "current": "0.4.0",
      "next": "0.4.1",
      "kind": "patch",
      "reasons": [
        {
          "kind": "mirror",
          "upstream": "api",
          "file": "charts/myapp/Chart.yaml",
          "key": "appVersion"
        }
      ]
    }
  }
}
```

Reason kinds: `commit`, `trigger`, `mirror`, `manual` (e.g. an explicit
`--finalize`). Each carries its own structured fields.

`multicz explain <component>` zooms in on a single component with the
full per-commit breakdown — useful when the plan looks unexpected and
you want to see *which files* of a commit actually mapped to the
component:

```
Component: api
  Current version: 1.2.0
  Next version:    1.3.0 (minor)

Reasons:
  1. abc1234 feat(api): add login flow
      SHA:   abc1234...
      Type:  feat(api) → minor
      Files matched in this component:
        - src/auth.py
        - src/main.py
```

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

### Debian packages (`format = "debian"`)

`multicz` writes a proper `debian/changelog` instead of a markdown
`CHANGELOG.md` for components built as `.deb`:

```toml
[components.mypkg]
paths  = ["debian/**", "src/**"]
format = "debian"

[components.mypkg.debian]
changelog       = "debian/changelog"     # default
distribution    = "UNRELEASED"           # default — change to "unstable" before upload
urgency         = "medium"               # default
debian_revision = 1                      # appended as -<n> to the upstream version
# maintainer    = "Name <email>"         # falls back to debian/control then git config
# epoch         = 2                      # rare, prepended as "<n>:"
```

On `multicz bump`, the upstream version is read from the topmost stanza
of `debian/changelog`, the new upstream is computed from the conventional
commits since the last tag, and a fresh stanza is **prepended** to the
file:

```
mypkg (1.3.0-1) UNRELEASED; urgency=medium

  * feat: Add login flow
  * fix(api): Null token on logout

 -- Chris <chris@example.com>  Fri, 01 May 2026 10:01:44 +0000

mypkg (1.2.3-1) unstable; urgency=medium

  * Initial release.

 -- Chris <chris@example.com>  Sun, 01 Jan 2023 00:00:00 +0000
```

Old stanzas are never rewritten, matching the contract of `dch(1)`.

### Auto-discovery languages

`multicz init` detects the following manifests across the working tree
and seeds one component per project:

| ecosystem | manifest | name source |
|---|---|---|
| Python | `**/pyproject.toml` | `[project].name` (PEP 621 / uv / hatch / modern Poetry) **or** `[tool.poetry].name` (legacy Poetry) — `[tool.uv.workspace].members` and `exclude` are honoured |
| Helm | `**/Chart.yaml` | `name:` field |
| Rust | `**/Cargo.toml` | `[package].name` (workspaces collapse to one component when `[workspace.package].version` is shared) |
| Go | `**/go.mod` | last segment of `module …` (strips `/vN`) — tag-driven, no version file |
| Gradle | root `gradle.properties` with `version=` | `rootProject.name` from `settings.gradle[.kts]` |
| Node.js | root `package.json` (or workspace members via `workspaces` / `pnpm-workspace.yaml`) | `name` field (npm scopes stripped) |
| Debian | `debian/changelog` | package name from the top stanza header |

Common noise dirs (`.git`, `node_modules`, `.venv`, `target`, `build`,
`dist`, `vendor`, …) are excluded from the scan.

## Configuration reference

See [`examples/fastapi-helm/multicz.toml`](examples/fastapi-helm/multicz.toml)
for a fully commented example.

## Tagging strategy

Each component gets its own git tag whose name is built from
`tag_format`, with two placeholders:

| placeholder | substituted with |
|---|---|
| `{component}` | the component name (the dict key, or `name` in array form) |
| `{version}` | the new version produced by the bump |

The default is `tag_format = "{component}-v{version}"` so a typical
release looks like:

```
api-v1.3.0
api-v1.4.0-rc.1
chart-v0.5.0
frontend-v2.1.0
mypkg-v1.3.0          # debian-format components keep semver in the tag
```

Tags are **annotated** (created with `-m`), which makes them work in
environments that have `tag.gpgSign = true` and lets `git describe`
land on them naturally.

### Per-component override

`tag_format` can be set on a component to override the project-wide
default:

```toml
[project]
tag_format = "{component}-v{version}"

[components.api]
paths = ["src/**", "pyproject.toml"]

[components.legacy]
paths = ["legacy/**"]
tag_format = "v{version}"          # keep the historical scheme
```

Each component's rendered prefix (the bit before `{version}`) must be
unique across the project — otherwise `git tag --list <prefix>*` would
return tags from another component and the planner would read the
wrong "current" version. multicz refuses to load a config where two
components produce the same prefix and tells you which two to fix:

```
components 'foo' and 'bar' share the same tag prefix 'v'; tags would
collide. Set a unique tag_format on at least one of them.
```

### Migration from a single-tag scheme

A common starting point is a legacy repo with global tags like
`v1.2.0`, `v1.3.0`. To adopt multicz:

1. Decide whether the legacy tags belong to **one** of the new
   components (typically the main app). Set `tag_format = "v{version}"`
   on that component so its history continues seamlessly.
2. Give every other component a different prefix (the default
   `{component}-v{version}` does that for free).
3. The planner reads the current version using this priority — git
   tag matching the resolved `tag_format`, then the value in the
   component's primary `bump_file` (`pyproject.toml`'s
   `[project].version`, etc.), then `initial_version`. So even before
   you cut your first multicz tag, the in-tree version is honoured.

Concretely:

```toml
[project]
tag_format = "{component}-v{version}"

[components.api]
paths = ["src/**", "pyproject.toml"]
tag_format = "v{version}"          # legacy tags stay under "v" prefix

[components.chart]
paths = ["charts/**"]               # default "chart-v…" — fresh history
```

`multicz status` now shows `api` reading its version from the
existing `v1.2.0` tag while `chart` starts at `initial_version`.

## Helm chart immutability

Helm charts are content-addressed by `name-version.tgz`. If `chart-0.5.0`
references `appVersion: 1.2.0` in some pulls and `appVersion: 1.3.0` in
others, you've effectively shipped two different artifacts under the same
name. `multicz` refuses that: any time the mirrored `appVersion` changes,
the chart version moves with it.

## License

MIT
