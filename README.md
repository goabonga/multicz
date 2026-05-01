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
| `multicz init --print` | render the discovered config to stdout (no file written) |
| `multicz init --print --bare` | render the generic stub to stdout |
| `multicz init --detect` | summary of detected components without rendering full TOML |
| `multicz init --detect --output json` | machine-readable detection shape |
| `multicz status` | brief table of pending bumps with reason summaries |
| `multicz status --since origin/main` | preview the bump plan for a PR (vs main) |
| `multicz changed` | components with files changed since their last tag (CI matrix) |
| `multicz changed --since origin/main` | what changed in this branch vs main |
| `multicz plan` | per-component plan with explicit reasons (commit / trigger / mirror) |
| `multicz plan --since <ref>` | recompute the plan against a custom baseline |
| `multicz explain <comp> --since <ref>` | scope explain to a specific window |
| `multicz plan --output json` | machine-readable shape for CI |
| `multicz explain <component>` | full breakdown — every commit, the matched files, every cascade |
| `multicz bump` | apply bumps to all configured files |
| `multicz bump --dry-run` | plan without writing |
| `multicz bump --commit --tag` | release in one shot: write, commit, tag |
| `multicz bump --commit --tag --push` | …and push commit + tags with `--follow-tags` |
| `multicz bump --commit -m "..."` | verbatim release-commit message (overrides the template) |
| `multicz bump --force api:patch` | manual bump for rebuilds without commits |
| `multicz bump --force api:minor --force chart:major` | repeatable across components |
| `multicz bump --output json` | emit `{"bumps": {...}, "git": {...}}` for CI |
| `multicz get <component>` | read the current version from the primary bump file |
| `multicz changelog [-c name]` | per-component conventional-commit log since the last tag |
| `multicz changelog --output md` | the same, grouped into Breaking / Features / Fixes / Perf / Other |
| `multicz release-notes <comp>` | one-shot release notes for the upcoming bump (no file written) |
| `multicz release-notes --tag <tag>` | retrospective notes for a past release tag |
| `multicz release-notes --all --output md` | one block per bumping component, ready for `gh release create` |
| `multicz bump --no-changelog` | bump versions without touching declared `CHANGELOG.md` files |
| `multicz bump --pre rc` | enter / continue a release-candidate cycle (`1.2.3` → `1.3.0-rc.1` → `1.3.0-rc.2`) |
| `multicz bump --finalize` | drop a pre-release suffix (`1.3.0-rc.2` → `1.3.0`) — works with no new commits |
| `multicz check <file>` | validate a commit message — wire as a `commit-msg` hook |
| `multicz artifacts <comp>` | list what CI should build/push for the current version |
| `multicz artifacts --all --output json` | machine-readable artifact refs for the whole repo |
| `multicz validate` | run every config + repo sanity check (CI gate) |
| `multicz state` | inspect the optional persistent state file (audit trail) |
| `multicz validate --strict` | also fail on warnings (overlapping paths, useless mirrors, …) |
| `multicz validate --output json` | machine-readable findings shape |

### Version scheme (semver vs PEP 440)

Pre-release versions render differently across ecosystems:

| ecosystem | form | example |
|---|---|---|
| npm, Cargo, Helm, generic | semver 2.0 | `1.3.0-rc.1` |
| Python (canonical PEP 440) | dotless | `1.3.0rc1` |
| Debian source packages | tilde | `1.3.0~rc1` |

The default `version_scheme = "semver"` works for npm, Cargo, Helm,
and is **also accepted** by PEP 440 (just normalized internally). For
projects that want strict canonical Python output, opt into pep440
per-component:

```toml
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
version_scheme = "pep440"

[components.chart]
paths = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
# default semver — Helm requires it
```

A run of `multicz bump --pre rc --commit --tag` writes:

```
pyproject.toml      version = "1.3.0rc1"
charts/.../Chart.yaml
  version:    0.4.1-rc.1     ← chart's own scheme (semver)
  appVersion: 1.3.0rc1       ← mirror copies api's rendered form
git tags
  api-v1.3.0rc1
  chart-v0.4.1-rc.1
```

PEP 440 compact label aliases are applied on output: `--pre alpha`
with `scheme = "pep440"` produces `1.3.0a1` (canonical), not
`1.3.0alpha1`. Both forms are still parseable, so ordering and
re-reads stay correct across schemes.

`format = "debian"` is incompatible with `version_scheme = "pep440"` —
the Debian flow uses semver internally and applies its own
`~rc1` notation at write time. Configs that combine the two are
rejected at load.

### Empty release / manual bump

When there are no commits the planner can act on, `multicz bump` is a
no-op:

```
$ multicz bump
no bumps pending — use --force <name>:<kind> for a manual bump
```

Exit code is 0 — "nothing to do" is success, not failure.

For the cases where you genuinely need a release without code changes
(weekly base-image rebuild for security patches, dependency-only
update, deliberate retag), `--force NAME:KIND` is the manual escape
hatch:

```sh
# Single forced bump
multicz bump --force api:patch

# Multiple components in one go
multicz bump --force api:minor --force chart:major

# Compose with --pre / --finalize / --commit / --tag
multicz bump --force api:minor --pre rc --commit --tag
```

`--force` shows up in the plan and explain output as a `ManualReason`
so the audit trail is preserved:

```json
{
  "kind": "manual",
  "note": "--force api:patch"
}
```

Promotion semantics: if the component would already bump from commits,
`--force` is **upgraded** (never downgraded). A `feat:` (minor) plus
`--force api:patch` stays at minor; `feat:` plus `--force api:major`
jumps to major. The strongest level always wins.

Validation is upfront and explicit:

```
$ multicz bump --force api:weird
invalid kind 'weird': must be major, minor, or patch
exit=1

$ multicz bump --force unknown:patch
unknown component: unknown
exit=1

$ multicz bump --force no-colon
invalid --force spec 'no-colon': expected NAME:KIND (e.g. api:patch)
exit=1
```

`--force` does **not** add anything to the changelog (no commit to
list), so the rendered `CHANGELOG.md` will say
`_No notable changes._` for the forced section. If you want a custom
note, also pass `--commit-message`:

```sh
multicz bump --force api:patch --commit \
  -m "chore(release): rebuild api for CVE-2024-1234"
```

### Release commit message

`multicz bump --commit` writes a single release commit. Its message
is rendered from `[project].release_commit_message`, which defaults
to:

```
chore(release): bump {summary}

{body}
```

Producing the historical shape:

```
chore(release): bump api 1.2.0 -> 1.3.0, chart 0.4.0 -> 0.5.0

- api: 1.2.0 -> 1.3.0 (minor)
- chart: 0.4.0 -> 0.5.0 (patch)
```

Available placeholders:

| placeholder | example |
|---|---|
| `{summary}` | `api 1.2.0 -> 1.3.0, chart 0.4.0 -> 0.5.0` |
| `{components}` | `api v1.3.0, chart v0.5.0` |
| `{body}` | bullet list with kind annotations |
| `{count}` | `2` |

Examples:

```toml
[project]
# Compact one-liner
release_commit_message = "chore(release): {components}"
# -> chore(release): api v1.3.0, chart v0.5.0

# Spell out the count
release_commit_message = "release: {count} components ({summary})"
# -> release: 2 components (api 1.2.0 -> 1.3.0, chart 0.4.0 -> 0.5.0)
```

Literal `{` and `}` must be escaped as `{{` / `}}`.

For one-off releases, override the entire message with `-m`:

```sh
multicz bump --commit --tag -m "release: hotfix for the production outage"
```

`-m` is verbatim like `git commit -m` — no placeholders are expanded.

> **If you change the prefix**, also update
> `release_commit_pattern` so the auto-filter still matches:
> ```toml
> release_commit_pattern  = "^release"
> release_commit_message  = "release: {components}"
> ```

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

### Choosing the commit window (`--since`)

By default, every component compares against **its own** latest tag:
the planner picks `api-v1.2.0` for `api` and `chart-v0.5.0` for `chart`,
each scoped to that component's tag prefix. That's the right behaviour
when you're cutting a release from `main`.

For other workflows, override the reference globally with `--since`:

| use case | command |
|---|---|
| PR preview ("what would bump if I merge this branch?") | `multicz plan --since origin/main` |
| What changed in this branch (for CI matrix) | `multicz changed --since origin/main` |
| Inspect commits from a specific point | `multicz status --since HEAD~10` |
| Migrate from a legacy global tag scheme | `multicz plan --since v1.0.0` |
| Recover from removed/recreated tags | `multicz plan --since <known sha>` |

`--since` accepts anything `git rev-parse` accepts: tags, branches,
SHAs, `HEAD~N`, etc.

The override only moves the **commit window** used to compute bump
kinds. The "current version" resolution (latest tag → primary
`bump_file` → `initial_version`) is unaffected — so even with
`--since origin/main`, the planner still bumps from the latest
released version, not from main. That's deliberate: PRs preview the
"if merged" version without re-deriving history.

`bump` intentionally does **not** take `--since`. Combining a custom
window with a write+tag is a footgun (you can create tags that
contradict the actual history). Workflow:

```sh
multicz plan --since origin/main          # preview
# … inspect, decide …
multicz bump --commit --tag --push        # run the regular bump
```

### `changed` (CI matrix gating)

`multicz changed` is the lightest possible question — *did anything
change* — designed for CI to only run jobs for the components a PR
actually touched. Distinct from `plan`: `plan` says "would bump",
`changed` says "any activity, regardless of whether it's release-
worthy".

```sh
multicz changed                       # per-component (since each one's last tag)
multicz changed --since origin/main   # every component vs main (PR gating)
multicz changed --output json
```

Default text output is one component name per line — pipeable into
shell loops:

```sh
for comp in $(multicz changed --since origin/main); do
  echo "rebuilding $comp"
done
```

JSON output exposes both lists, ideal for `fromJson` in GitHub Actions
matrices:

```yaml
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      changed: ${{ steps.c.outputs.list }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - id: c
        run: |
          echo "list=$(multicz changed --since origin/main \
                       --output json | jq -c .changed)" >> $GITHUB_OUTPUT

  test:
    needs: detect
    if: needs.detect.outputs.changed != '[]'
    strategy:
      matrix:
        component: ${{ fromJson(needs.detect.outputs.changed) }}
    runs-on: ubuntu-latest
    steps:
      - run: cd ${{ matrix.component }} && make test
```

Release commits matching `project.release_commit_pattern` are
filtered out so a previous `multicz bump --commit` doesn't keep
flagging every component forever.

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
CI step needs to gate releases or post a comment on a PR. `schema_version`
lets consumers guard against future breaking changes:

```json
{
  "schema_version": 1,
  "bumps": {
    "api": {
      "current_version": "1.2.0",
      "next_version": "1.3.0",
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
      ],
      "artifacts": [
        {"type": "docker", "ref": "ghcr.io/foo/api:1.3.0"}
      ]
    },
    "chart": {
      "current_version": "0.4.0",
      "next_version": "0.4.1",
      "kind": "patch",
      "reasons": [
        {
          "kind": "mirror",
          "upstream": "api",
          "file": "charts/myapp/Chart.yaml",
          "key": "appVersion"
        }
      ],
      "artifacts": []
    }
  }
}
```

Canonical `jq` queries CI scripts can rely on:

```sh
# anything pending?
multicz plan --output json | jq -e '.bumps | length > 0'

# a single component's next version
multicz plan --output json | jq -r '.bumps.api.next_version'

# every Docker ref to push (after bump --output json)
multicz bump --commit --tag --output json | \
  jq -r '.bumps[].artifacts[] | select(.type == "docker") | .ref'

# tags freshly created (from bump output, with --tag)
multicz bump --commit --tag --output json | jq -r '.git.tags[]'
```

End-to-end pipelines for the three big platforms are in
[`examples/ci/`](examples/ci/):

| platform | workflow file |
|---|---|
| GitHub Actions | [`examples/ci/github-actions/release.yml`](examples/ci/github-actions/release.yml) |
| GitLab CI/CD | [`examples/ci/gitlab-ci.yml`](examples/ci/gitlab-ci.yml) |
| Azure Pipelines | [`examples/ci/azure-pipelines.yml`](examples/ci/azure-pipelines.yml) |

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

### Release notes (`gh release create`)

`multicz release-notes` is the single-shot, no-file-written counterpart
to the persistent `CHANGELOG.md`. Designed to be piped into
`gh release create` or pasted into a GitHub/GitLab Release UI.

```sh
gh release create api-v1.3.0 --notes "$(multicz release-notes --tag api-v1.3.0)"
```

Three modes:

```sh
# upcoming bump for one component (preview before `multicz bump --tag`)
multicz release-notes api

# upcoming bumps for every bumping component (one --all output to paste)
multicz release-notes --all

# retrospective: what shipped in a past tagged release
multicz release-notes --tag api-v1.3.0
```

Critical detail for past tags: the previous-tag lookup is
**stable-aware**. A stable release tag (`api-v1.3.0`) reads commits
since the previous *stable* tag (`api-v1.2.0`) — not since the most
recent RC — so the notes consolidate everything that shipped in 1.3.0
over the whole RC cycle. A pre-release tag (`api-v1.3.0-rc.2`) reads
commits since the immediately previous tag (`api-v1.3.0-rc.1`) so
each RC only shows the delta.

Output formats:

- `md` (default) — sections (`### Features`, `### Fixes`, …) and bullets
- `text` — plain ASCII, useful in `git log`-style scripts
- `json` — `{"sections": [{"component": "...", "from_version": "...",
  "to_version": "...", "commits": [...]}]}` for further processing

The body honours every project-level rendering knob:
`changelog_sections`, `breaking_section_title`, `other_section_title`,
`ignored_types`. So whatever shape your `CHANGELOG.md` takes,
`release-notes` produces identical sections.

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

### `init` modes

`multicz init` has three output modes that compose with the existing
`--bare` flag:

```sh
# default: discover the working tree, write multicz.toml
multicz init

# render the discovered config to stdout, no file written
multicz init --print > custom-name.toml

# render the generic stub to stdout (composes with --bare)
multicz init --print --bare

# inspection only — show what would be detected, no rendering
multicz init --detect

# machine-readable detection (paths, bump_files, mirrors, format, …)
multicz init --detect --output json
```

`--print` and `--detect` are non-destructive: the filesystem is
untouched, so they're safe to run inside CI without `--force`.

`--detect` is the lightest possible answer to *"what would init pick up
in this repo?"*:

```
$ multicz init --detect
Detected 2 component(s):
  • api (pyproject.toml)
      mirrors → charts/myapp/Chart.yaml:appVersion
  • myapp (charts/myapp/Chart.yaml)
```

`--print` returns the byte-for-byte TOML — pipe it into a file with a
custom name, or into a diff against an existing config. Combinations
rejected at parse time: `--detect + --bare` and `--detect + --print`.

### Workspace rules

The user's natural worry: *"what happens with nested workspaces?"*. Four
explicit rules govern how `multicz init` resolves them.

#### 1. Is the root manifest a component?

| ecosystem | root has version? | root has workspace block? | root → component? |
|---|---|---|---|
| Python | `[project].version` set | with `[tool.uv.workspace]` | **yes** |
| Python | no `[project]` table | with `[tool.uv.workspace]` | **no** (orchestrator) |
| Cargo | `[package]` set | with `[workspace]` | **yes** |
| Cargo | no `[package]` | with `[workspace]` | **no** (virtual workspace) |
| Node.js | any `version` | `workspaces` declared | **no** (members only) |
| Node.js | `version` set | no `workspaces` | **yes** (single-package) |

A workspace orchestrator with no version is **never** a component — its
job is to delegate, not to ship. A root that doubles as a package
(common for Python and Cargo) IS a component, alongside its members.

#### 2. Do workspace members inherit the version?

Each ecosystem decides:

| ecosystem | per-member? | shared? |
|---|---|---|
| uv (`[tool.uv.workspace]`) | members own their `[project].version` | — |
| Cargo `[workspace.package].version` | when present, members inherit via `version.workspace = true` | yes |
| Cargo without `workspace.package.version` | members own their `[package].version` | — |
| npm/yarn/pnpm `workspaces` | each `package.json` has its own `version` | — |

When Cargo declares `[workspace.package].version`, multicz collapses
the workspace into a **single component** bumping that one key.
Members that inherit are silently skipped to avoid double-bumping.
Mixed members (some inheriting, some declaring their own `[package].version`)
are not currently supported — declare uniformly.

#### 3. Are excluded members really ignored?

| declaration | excludes |
|---|---|
| `[tool.uv.workspace].exclude = ["packages/legacy"]` | uv |
| `[workspace].exclude = ["crates/legacy"]` | Cargo |
| `"workspaces": ["packages/*", "!packages/legacy"]` | npm / yarn |
| `pnpm-workspace.yaml`: `packages: ['packages/*', '!packages/legacy']` | pnpm |

All four are honored — excluded members never appear as components.
The cross-ecosystem rule is consistent: if the workspace declaration
excludes a path, multicz skips it.

#### 4. What if two manifests share the same name?

`_unique` auto-suffixes the second one with the manifest type:

| collision | result |
|---|---|
| python `api` + chart `api` | `api`, `api-chart` |
| python `api` + python `api` (rare) | `api`, `api-py` |
| chart `foo` + chart `foo` (different dirs) | `foo`, `foo-chart-2` |

Suffix order is deterministic — the **first** manifest discovered keeps
the bare name. To force a different naming, edit `multicz.toml`
manually after `init` (the discovery only runs at `init` time; the
planner reads whatever names you've declared).

#### Reference layout (covered by integration tests)

```
repo/
├── pyproject.toml              # root: [project] + [tool.uv.workspace]
├── services/
│   ├── api/pyproject.toml      # uv workspace member
│   └── worker/pyproject.toml   # uv workspace member
├── packages/
│   └── client/package.json     # npm package (no workspace block)
└── charts/
    └── api/Chart.yaml          # name collides with services/api
```

`multicz init` produces:

| component | source | mirrors |
|---|---|---|
| `monorepo` | root pyproject (workspace + `[project]`) | — |
| `api` | `services/api/pyproject.toml` | → `charts/api/Chart.yaml:appVersion` |
| `worker` | `services/worker/pyproject.toml` | none (no chart with that name) |
| `client` | `packages/client/package.json` | — |
| `api-chart` | `charts/api/Chart.yaml` (suffixed: collides with python `api`) | — |

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

## Artifacts (what CI should build and push)

`multicz` does **not** build or push artifacts itself. It surfaces the
information CI needs to do so, decoupled from your specific image
registry, chart repository, or package index. Declare what each
component publishes:

```toml
[components.api]
paths = ["src/**", "pyproject.toml"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

[[components.api.artifacts]]
type = "docker"
ref  = "ghcr.io/foo/api:{version}"

[[components.api.artifacts]]
type = "docker"
ref  = "registry.acme.com/api:{version}"

[components.chart]
paths = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]

[[components.chart.artifacts]]
type = "helm"
ref  = "{component}-{version}.tgz"

[[components.chart.artifacts]]
type = "oci"
ref  = "oci://registry.acme.com/charts/{component}:{version}"
```

`ref` accepts `{version}` and `{component}` placeholders. `type` is
free-form so CI can filter on it (`docker`, `helm`, `oci`, `npm`,
`pypi`, …).

Three places surface the rendered artifacts:

```sh
# Direct lookup against the current version
multicz artifacts api
# api (1.2.0)
#   [docker] ghcr.io/foo/api:1.2.0
#   [docker] registry.acme.com/api:1.2.0

# Against an explicit target version
multicz artifacts api --version 1.4.0-rc.1

# JSON for CI scripts
multicz artifacts --all --output json
```

`multicz plan --output json` and `multicz bump --output json` both
include an `artifacts` array per component rendered against the
*planned* (or just-applied) version. CI can drive the actual
build/push from a single payload:

```yaml
- run: |
    RELEASE=$(multicz bump --commit --tag --output json)
    echo "$RELEASE" | jq -r '.bumps[].artifacts[] | select(.type=="docker") | .ref' \
      | xargs -I{} sh -c 'docker build -t {} . && docker push {}'
    echo "$RELEASE" | jq -r '.bumps[].artifacts[] | select(.type=="helm") | .ref' \
      | xargs -I{} sh -c 'helm package . && helm push {}'
```

## Optional state file

`multicz` is normally stateless — every command recomputes from git
tags and the in-tree manifests. For monorepos that want a persistent
audit trail or **drift detection** (catch manual edits that bypassed
`multicz bump`), opt into a state file:

```toml
[project]
state_file = ".multicz/state.json"
```

After every successful `multicz bump`, the file is written next to the
version updates and lands in the release commit (when `--commit` is
used):

```json
{
  "version": 1,
  "git_head": "fe9a637d223e570fc873ecac9ee4e53c3c05ee31",
  "git_head_short": "fe9a637",
  "timestamp": "2026-05-01T17:46:27Z",
  "components": {
    "api": {
      "version": "1.3.0",
      "tag": "api-v1.3.0",
      "tag_sha": null
    }
  }
}
```

`multicz state` prints the snapshot. `multicz state --output json`
emits the same JSON for `jq` consumption.

### Drift detection in `validate`

When `state_file` is set, `multicz validate` adds two checks:

* **`state_drift`** (warning) — the recorded version doesn't match the
  current value in the primary `bump_file`. Fires when someone edits
  `pyproject.toml` / `Chart.yaml` / `package.json` manually without
  going through `multicz bump`:
  ```
  ! api: state recorded version '1.3.0' but pyproject.toml now reads
    '9.9.9' — someone may have edited the file outside multicz bump
    (state_drift)
  ```
* **`state_unknown_component`** (warning) — the state references a name
  no longer declared in `multicz.toml` (typically after a component
  was renamed or removed without clearing state).

The state file is **opt-in**. The default stateless flow remains the
recommended setup for most repos — the planner always re-derives from
git, which is the source of truth.

## Path ownership and overlap

The matcher uses **first-match-wins** by default: when two components
both claim a file (e.g. `api` and `worker` both listing `src/**`), the
component declared first in the config silently owns it, and the
others lose. That's predictable but easy to miss.

`project.overlap_policy` makes the choice explicit:

```toml
[project]
overlap_policy = "error"   # default
```

| value | `validate` | runtime behaviour |
|---|---|---|
| `error` (default) | error | refuses to plan/bump until you resolve the overlap |
| `first-match` | warning | first-declared component owns the file (the others lose) |
| `allow` | silent | same runtime as `first-match` — suppresses the finding |
| `all` | info | a shared file bumps **every** claiming component |

The `all` mode is genuinely useful for monorepos where several
components share code:

```toml
[project]
overlap_policy = "all"

[components.api]
paths = ["src/**", "pyproject.toml"]

[components.worker]
paths = ["src/**", "workers/**"]
```

A `feat:` commit touching `src/common.py` now bumps both `api` and
`worker`. With `error` (the default) that same commit refuses to plan
until you tighten the paths or add `exclude_paths`.

## Bump kind by commit type

| commit | bump |
|---|---|
| `feat: …` | minor |
| `feat!: …` or `BREAKING CHANGE:` footer | major |
| `fix: …` | patch |
| `perf: …` | patch |
| `revert: …` | patch — a revert is user-visible activity |
| `chore`, `docs`, `style`, `test`, `build`, `ci`, `refactor` | none |
| anything not matching `<type>(<scope>)?: <subject>` | controlled by `unknown_commit_policy` (default: ignored) |

A `revert: feat(api): drop login` is treated as a `patch` because
something user-visible changed — a feature was removed (or restored).
The conservative bump avoids saying "no change" when there clearly
was one. Override per-component with `bump_policy = "scoped"` if you
need a tighter scope rule, or with `ignored_types = ["revert"]` if
you really want them silent.

The default `[project].changelog_sections` now includes a `Reverts`
section so reverted commits show up in `CHANGELOG.md` and
`release-notes` output:

```markdown
## [1.3.1] - 2026-05-01

### Reverts

- drop login flow (`abc1234`)
```

The section only renders when the release window contains revert
commits — projects without reverts see the same output as before.

## Non-conventional commits

A commit like `update stuff` (no `<type>:` prefix) doesn't fit the
conventional grammar. The default behaviour silently skips it — but
that can hide real activity. `project.unknown_commit_policy` makes
the choice explicit:

```toml
[project]
unknown_commit_policy = "ignore"   # default
# or "patch"
# or "error"
```

| value | planner behaviour |
|---|---|
| `ignore` (default) | silent skip — backwards-compatible |
| `patch` | the commit produces a `NonConventionalReason` at patch level, visible in `plan` / `explain` / JSON |
| `error` | refuse to plan, list every offending SHA with a remediation hint |

`error` mode renders a clean CLI message instead of a traceback:

```
$ multicz plan
✗ 2 non-conventional commit(s) blocking the plan (unknown_commit_policy='error')
  - 1b233e5: update stuff
  - 53f374b: wip

Either rewrite their headers as conventional commits (`git rebase -i`),
or set unknown_commit_policy = "ignore" (or "patch") in [project].
```

Use it in CI as a strict gate; `ignore` (default) keeps the existing
laissez-faire experience.

## Ignoring commit types

Some commit types should never appear in any bump or changelog —
typically `chore(deps):` updates that incidentally touch `src/`, or
`ci: tweak workflow.yml` against a `.github/**` path owned by a
component. `ignored_types` makes that explicit:

```toml
[project]
ignored_types = ["chore", "ci", "docs", "test", "style"]
```

You can also opt-in per-component (the effective set is the union):

```toml
[components.api]
ignored_types = ["fix"]   # api ignores 'fix' on top of project-wide rules
```

A commit whose type is in the effective set is fully filtered:

| | with `ignored_types = ["chore", "ci"]` |
|---|---|
| `feat: real change` | ✓ bumps, in changelog |
| `fix: bug` | ✓ bumps, in changelog |
| `chore(deps): bump typer` | ✗ ignored |
| `ci: tweak release workflow` | ✗ ignored |

The filter is stricter than `release_commit_pattern` (which targets
one specific message shape): `ignored_types` short-circuits before
the bump kind is even consulted, so `feat!: ...` is also dropped
if `feat` is in the list. That's the explicit cost of the choice.

## Per-component bump policy

When a single commit touches multiple components, each component
*also* gets that commit's bump kind by default. So a:

```
feat: change API contract and update Helm values
```

with files in both `src/` and `charts/myapp/values.yaml` bumps **api**
*and* **chart** to minor — even though the chart only got a config
tweak.

Components that want stricter semantics can opt into
`bump_policy = "scoped"`:

```toml
[components.chart]
paths = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
bump_policy = "scoped"
```

| commit | api | chart |
|---|---|---|
| `feat: cross-cutting change` (no scope) | minor | minor — no scope means "applies broadly" |
| `feat(api): rewrite contract` | minor (scope matches) | **patch** — demoted, scope ≠ chart |
| `feat(chart): add value` | — | minor (scope matches) |
| `fix: typo` | patch | patch (already patch, no demotion) |

The demotion is surfaced explicitly in `multicz explain`:

```
2. af74ec5 feat(api): rewrite contract
    Type:  feat(api) → patch
    Demoted from minor (bump_policy='scoped', different scope)
```

…and in the JSON output:

```json
{"kind": "commit", "type": "feat", "scope": "api",
 "bump_kind": "patch", "original_kind": "minor", ...}
```

Two values are supported:

- `as-commit` (default): the commit's natural kind applies to every
  touched component. Matches semantic-release / lerna / nx semantics.
- `scoped`: when a commit's scope names a different component,
  demote `minor`/`major` to `patch`. No-scope commits still propagate
  as-is.

## Helm chart immutability

Helm charts are content-addressed by `name-version.tgz`. If `chart-0.5.0`
references `appVersion: 1.2.0` in some pulls and `appVersion: 1.3.0` in
others, you've effectively shipped two different artifacts under the same
name. `multicz` refuses that: any time the mirrored `appVersion` changes,
the chart version moves with it.

## License

MIT
