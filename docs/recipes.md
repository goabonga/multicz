---
icon: lucide/chef-hat
---

# Recipes

## FastAPI + Helm { #fastapi-helm }

A FastAPI service shipped with a Helm chart. Layout:

```
repo/
├── src/                  # Python sources
├── pyproject.toml        # canonical api version
├── Dockerfile            # built from the api version
└── charts/myapp/
    ├── Chart.yaml        # version + appVersion
    ├── templates/        # kubernetes manifests
    └── values.yaml
```

Config:

```toml
[project]
commit_convention = "conventional"
tag_format        = "{component}-v{version}"
initial_version   = "0.1.0"

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

Behaviour:

| change | api | image tag | chart.version | appVersion |
|---|---|---|---|---|
| `src/main.py` (feat) | minor | follows api | patch (cascade) | mirror |
| `Dockerfile` (CVE base) | patch | follows api | patch (cascade) | mirror |
| `charts/myapp/templates/dep.yaml` | — | — | patch | — |
| `charts/myapp/values.yaml` (config) | — | — | patch | — |

The Docker image tag is `api.version` itself — read it from CI:

```bash
TAG=$(multicz get api)
docker build -t registry/myapp:$TAG .
docker push registry/myapp:$TAG
helm package charts/myapp
```

The full commented config lives at
[`examples/fastapi-helm/multicz.toml`](https://github.com/goabonga/multicz/blob/main/examples/fastapi-helm/multicz.toml).

## CI matrix gating { #ci-matrix-gating }

Use `multicz changed` to only run jobs for components a PR actually
touched.

```yaml
jobs:
  detect:
    runs-on: ubuntu-latest
    outputs:
      changed: ${{ steps.c.outputs.list }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: pipx install multicz
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
      - uses: actions/checkout@v4
      - run: cd ${{ matrix.component }} && make test
```

`fetch-depth: 0` is required so `--since origin/main` can resolve the
merge base.

## One-shot CI release { #ci-release }

```yaml
- run: |
    multicz validate --strict
    RELEASE=$(multicz bump --commit --tag --push --output json)

    # Build/push every declared docker artifact
    echo "$RELEASE" | jq -r '.bumps[].artifacts[] | select(.type=="docker") | .ref' \
      | xargs -I{} sh -c 'docker build -t {} . && docker push {}'

    # Package/push every declared helm artifact
    echo "$RELEASE" | jq -r '.bumps[].artifacts[] | select(.type=="helm") | .ref' \
      | xargs -I{} sh -c 'helm package . && helm push {}'
```

End-to-end pipelines for GitHub Actions, GitLab CI, and Azure Pipelines
live under
[`examples/ci/`](https://github.com/goabonga/multicz/tree/main/examples/ci).

## Release candidates { #release-candidates }

A typical RC workflow:

```bash
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

The output format on the changelog after `--finalize` is governed by
[`finalize_strategy`](configuration.md#finalize_strategy) —
`consolidate` (default) lists every commit since the previous stable
tag, `promote` also drops the now-superseded RC sections, `annotate`
keeps each tag's section dedicated.

## Manual bump (empty release) { #manual-bump }

When there are no commits the planner can act on, `multicz bump` is a
no-op:

```
$ multicz bump
no bumps pending — use --force <name>:<kind> for a manual bump
```

Exit code is `0` — "nothing to do" is success, not failure.

For releases without code changes (weekly base-image rebuild for
security patches, dependency-only update, deliberate retag), use
`--force NAME:KIND`:

```bash
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
{ "kind": "manual", "note": "--force api:patch" }
```

Promotion semantics: if the component would already bump from commits,
`--force` is **upgraded** (never downgraded). A `feat:` (minor) plus
`--force api:patch` stays at minor; `feat:` plus `--force api:major`
jumps to major.

Validation is upfront and explicit:

- `--force api:weird` → `invalid kind 'weird': must be major, minor, or patch`
- `--force unknown:patch` → `unknown component: unknown`
- `--force no-colon` → `invalid --force spec 'no-colon': expected NAME:KIND`

`--force` does not add anything to the changelog (no commit to list).
For a custom note, also pass `--commit-message`:

```bash
multicz bump --force api:patch --commit \
  -m "chore(release): rebuild api for CVE-2024-1234"
```

## Release commit message { #release-commit-message }

`multicz bump --commit` writes a single release commit. Its message
is rendered from
`[project].release_commit_message` ([details][rcm]).

[rcm]: configuration.md#release_commit_message
Default:

```
chore(release): bump {summary}

{body}
```

Producing:

```
chore(release): bump api 1.2.0 -> 1.3.0, chart 0.4.0 -> 0.5.0

- api: 1.2.0 -> 1.3.0 (minor)
- chart: 0.4.0 -> 0.5.0 (patch)
```

Compact one-liner:

```toml
[project]
release_commit_message = "chore(release): {components}"
# -> chore(release): api v1.3.0, chart v0.5.0
```

Spell out the count:

```toml
[project]
release_commit_message = "release: {count} components ({summary})"
# -> release: 2 components (api 1.2.0 -> 1.3.0, chart 0.4.0 -> 0.5.0)
```

!!! warning "Update the pattern when changing the prefix"

    `release_commit_pattern` is the regex used to filter prior release
    commits out of the planner's input. If you change the prefix, also
    update the pattern so the auto-filter still matches:

    ```toml
    release_commit_pattern = "^release"
    release_commit_message = "release: {components}"
    ```

For one-off releases, override the entire message with `-m`:

```bash
multicz bump --commit --tag -m "release: hotfix for the production outage"
```

`-m` is verbatim like `git commit -m` — no placeholders are expanded.

## Migrating from a single-tag scheme { #migrating-from-a-single-tag-scheme }

A common starting point is a legacy repo with global tags like
`v1.2.0`, `v1.3.0`. To adopt multicz:

1. Decide whether the legacy tags belong to one of the new components
   (typically the main app). Set `tag_format = "v{version}"` on that
   component so its history continues seamlessly.
2. Give every other component a different prefix — the default
   `{component}-v{version}` does that for free.
3. The planner reads the current version with this priority — git tag
   matching the resolved `tag_format`, then the value in the
   component's primary `bump_file`, then `initial_version`. Even before
   you cut your first multicz tag, the in-tree version is honoured.

```toml
[project]
tag_format = "{component}-v{version}"

[components.api]
paths      = ["src/**", "pyproject.toml"]
tag_format = "v{version}"          # legacy tags stay under "v" prefix

[components.chart]
paths = ["charts/**"]               # default "chart-v…" — fresh history
```

`multicz status` now shows `api` reading its version from the existing
`v1.2.0` tag while `chart` starts at `initial_version`.

## Per-component lockfile sync { #post-bump }

Lockfiles need to track the new version multicz just wrote, otherwise a
subsequent `uv sync --frozen` (or `npm ci`, `cargo build --locked`) in
CI fails. Use `post_bump`:

```toml
[components.api]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
post_bump  = ["uv lock"]
```

Common one-liners:

| ecosystem | command |
|---|---|
| uv | `uv lock` |
| Poetry | `poetry lock --no-update` |
| npm | `npm install --package-lock-only` |
| pnpm | `pnpm install --lockfile-only` |
| Cargo | `cargo update --workspace` |
| Helm | `helm dependency update charts/foo` |
| Bundler | `bundle lock` |
| Composer | `composer update --lock` |
| Go modules | `go mod tidy` |

Files touched by these hooks are detected by content hash and folded
into the release commit, so the lockfile and the version it pins land
atomically.

## Drift detection in CI { #drift-detection }

Catch manual edits that bypassed `multicz bump`:

```toml
[project]
state_file = ".multicz/state.json"
```

In CI:

```bash
multicz validate --strict
```

`validate` adds a `state_drift` warning when the recorded version
doesn't match the current value in the primary `bump_file`. Treat it
as an error in your pipeline by passing `--strict`. See [optional
state file](concepts.md#optional-state-file).
