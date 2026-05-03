---
icon: lucide/cog
---

# Configuration

The full schema for `multicz.toml`. Sections also work under
`[tool.multicz]` in `pyproject.toml` or under `"multicz"` in
`package.json` (see [config discovery](concepts.md#config-discovery)).

## Project settings

The `[project]` table. All fields are optional.

### `commit_convention` { #commit_convention }

Literal `"conventional"`. Reserved for future grammars; only conventional
commits are supported today.

### `tag_format` { #tag_format }

Default `{component}-v{version}`. Two placeholders: `{component}` and
`{version}`. Each component's rendered prefix must be unique across the
project. Per-component override available on `[components.<name>]`.

### `initial_version` { #initial_version }

Default `"0.1.0"`. Used when a component has no tag, no `bump_files`
value, and nothing else to derive the current version from.

### `release_commit_pattern` { #release_commit_pattern }

Default `^chore\(release\)`. Regex matched against commit headers to
filter prior release commits out of the planner's input. Update this if
you customise [`release_commit_message`](#release_commit_message).

### `release_commit_message` { #release_commit_message }

Default:

```
chore(release): bump {summary}

{body}
```

Placeholders:

| placeholder | example |
|---|---|
| `{summary}` | `api 1.2.0 -> 1.3.0, chart 0.4.0 -> 0.5.0` |
| `{components}` | `api v1.3.0, chart v0.5.0` |
| `{body}` | bullet list with kind annotations |
| `{count}` | `2` |

Literal `{` / `}` must be escaped as `{{` / `}}`. See the [release
commit message recipe](recipes.md#release-commit-message).

### `changelog_sections` { #changelog_sections }

Default emits Features, Fixes, Performance, and Reverts. Declare your
own to customise the changelog vocabulary:

```toml
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

Sections render in declaration order, after the implicit Breaking
changes block. One commit type can appear in multiple sections.

### `breaking_section_title` { #breaking_section_title }

Default `"Breaking changes"`. Set to `""` to disable the breaking-changes
bucket (commits with `!` or `BREAKING CHANGE:` footers will then fall
into normal sections).

### `other_section_title` { #other_section_title }

Default `""`. When set (e.g. `"Misc"`), commits whose type matches no
declared section land here instead of being dropped.

### `cascade_section_title` { #cascade_section_title }

Default `"Dependencies"`. Section heading used in `CHANGELOG.md` when a
release is purely cascade-driven (mirror or trigger). Set to `""` to
disable and fall back to the legacy `_No notable changes._` placeholder.

### `cascade_changelog_format` { #cascade_changelog_format }

Default ``"Track `{upstream}` `{upstream_version}`"``. Format string
for each cascade entry. Placeholders: `{upstream}`, `{upstream_version}`.

### `finalize_strategy` { #finalize_strategy }

Default `"consolidate"`. Controls what `--finalize` writes into the
changelog.

| value | behaviour |
|---|---|
| `consolidate` | finalize section lists every commit since the previous *stable* tag (cumulative). RC sections stay below as history. |
| `promote` | same selection as `consolidate`, plus the now-superseded `## [1.3.0-rc.*]` markdown sections (and `~rc*-*` Debian stanzas) are removed. The final entry stands alone. |
| `annotate` | section lists only commits since the last tag (rc included). Each tag keeps its own dedicated section. |

### `overlap_policy` { #overlap_policy }

Default `"error"`. See [overlap policy](concepts.md#overlap-policy).

| value | `validate` | runtime |
|---|---|---|
| `error` | error | refuses to plan/bump |
| `first-match` | warning | first-declared owns the file |
| `allow` | silent | same as `first-match` |
| `all` | info | bumps every claiming component |

### `ignored_types` (project) { #ignored_types_project }

Default `[]`. Commit types that should never bump or appear in
changelogs. The filter short-circuits before bump kind is computed.

### `state_file` { #state_file }

Default `null`. Optional path (e.g. `.multicz/state.json`) for the
persistent state file written after every successful bump. Enables
[drift detection](concepts.md#optional-state-file) in `validate`.

### `unknown_commit_policy` { #unknown_commit_policy }

Default `"ignore"`. How to treat a commit that doesn't match
`<type>(<scope>)?: <subject>`.

| value | planner behaviour |
|---|---|
| `ignore` (default) | silent skip — backwards-compatible |
| `patch` | the commit produces a `NonConventionalReason` at patch level, visible in plan / explain / JSON |
| `error` | refuse to plan, list every offending SHA with a remediation hint |

### `sign_commits` { #sign_commits }

Default `false`. When `true`, the release commit is GPG-signed
(`git commit -S`). The `--sign` CLI flag also enables this; either
source enables signing.

### `sign_tags` { #sign_tags }

Default `false`. When `true`, every release tag is GPG-signed
(`git tag -s`).

### `trigger_policy` { #trigger_policy }

Default `"match-upstream"`. Controls how a `depends_on` cascade
computes the dependent's bump kind.

| value | behaviour |
|---|---|
| `match-upstream` | dependent inherits the upstream's kind (`api` minor → `chart` minor) |
| `patch` | dependent always patches when its upstream bumps |

## Component settings

The `[components.<name>]` table.

### `paths` { #paths }

Required, non-empty. Gitignore-style globs of files this component owns.

### `exclude_paths` { #exclude_paths }

Default `[]`. Globs subtracted from `paths`.

### `bump_files` { #bump_files }

Default `[]`. List of `{ file = "...", key = "..." }` pointing at the
canonical version literal(s). `key` is a dotted path; omit for plain
text files. Prefix with `regex:` for regex-based substitution
([details](concepts.md#regex-escape-hatch)).

### `mirrors` { #mirrors }

Default `[]`. Same shape as `bump_files`. Each mirror is rewritten with
the component's new version on every bump and may cascade a patch into
another component if it falls inside that component's `paths`.

### `depends_on` { #depends_on }

Default `[]`. Names of upstream components whose bumps should cascade
into this one. The legacy alias `triggers = [...]` still parses; both
fold into `depends_on`.

### `changelog` { #changelog }

Default `null`. Path to a `CHANGELOG.md` the planner should keep in
sync. The file is created with a small preamble on first use; subsequent
runs prepend a new keep-a-changelog section. Pass `--no-changelog` to
opt out for a single bump.

### `format` { #format }

Default `"default"`. Set to `"debian"` for components built as `.deb`.
With `format = "debian"`:

- `bump_files`, `mirrors`, and the top-level `changelog` are forbidden
  (the version is read from / written to `debian/changelog`),
- `version_scheme` must remain `"semver"` (the renderer applies its
  own `~rc1` notation),
- a `[components.<name>.debian]` table configures the stanza
  ([fields below](#debian-settings)).

### `tag_format` (component) { #tag_format_component }

Default `null` (inherit from `[project]`). Per-component override.
Useful for legacy migrations:

```toml
[components.api]
paths      = ["src/**", "pyproject.toml"]
tag_format = "v{version}"          # legacy tags stay under "v" prefix
```

### `bump_policy` { #bump_policy }

Default `"as-commit"`. Set to `"scoped"` to demote `minor`/`major` to
`patch` when the commit's scope names a different component. See [bump
policy](concepts.md#bump-policy).

### `ignored_types` (component) { #ignored_types_component }

Default `[]`. Per-component list of commit types to ignore. Effective
set is the union with `[project].ignored_types`.

### `version_scheme` { #version_scheme }

Default `"semver"`. Set to `"pep440"` for strict canonical Python
output. Incompatible with `format = "debian"`.

### `artifacts` { #artifacts }

Default `[]`. Declares what CI should build/push for this component.
`multicz` does not build or push — it surfaces the rendered refs.

```toml
[[components.api.artifacts]]
type = "docker"
ref  = "ghcr.io/foo/api:{version}"

[[components.api.artifacts]]
type = "docker"
ref  = "registry.acme.com/api:{version}"
```

`ref` accepts `{version}` and `{component}`. `type` is free-form
(`docker`, `helm`, `oci`, `npm`, `pypi`, `github-release`, …).

Surfaced via `multicz artifacts`, and embedded inside
`multicz plan --output json` and `multicz bump --output json` per
component (rendered against the planned/applied version).

### `post_bump` { #post_bump }

Default `[]`. Shell commands run after multicz has rewritten this
component's `bump_files` but before staging for the release commit.
Canonical use-case: regenerating lockfiles that depend on the version
multicz just wrote.

```toml
[components.api]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
post_bump  = ["uv lock"]
```

Each entry is parsed via `shlex.split` and executed in the repo root.
Files modified by these hooks are auto-detected (by content hash) and
joined to the release commit, so the lockfile and the version it pins
land atomically. Common commands: `uv lock`, `npm install
--package-lock-only`, `cargo update --workspace`,
`helm dependency update charts/foo`, `bundle lock`,
`composer update --lock`, `go mod tidy`. Bad quoting surfaces at
`multicz validate`.

## Debian settings { #debian-settings }

The `[components.<name>.debian]` table. Only valid when
`format = "debian"`.

| field | default | meaning |
|---|---|---|
| `changelog` | `debian/changelog` | path to the source `debian/changelog` |
| `distribution` | `UNRELEASED` | distribution field on the new stanza (change to `unstable` before upload) |
| `urgency` | `medium` | `urgency=` on the new stanza |
| `maintainer` | `null` | `Name <email>`. Falls back to `Maintainer:` in `debian/control`, then `git config user.name`/`user.email`, then a placeholder. |
| `debian_revision` | `1` | appended as `-<n>` to the upstream version |
| `epoch` | `null` | rare; prepended as `<n>:` |

## Full example

```toml
[project]
commit_convention      = "conventional"
tag_format             = "{component}-v{version}"
initial_version        = "0.1.0"
overlap_policy         = "error"
unknown_commit_policy  = "ignore"
state_file             = ".multicz/state.json"

[components.api]
paths      = ["src/**", "pyproject.toml", "tests/**", "Dockerfile"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]
mirrors    = [{ file = "charts/myapp/Chart.yaml", key = "appVersion" }]
changelog  = "CHANGELOG.md"
post_bump  = ["uv lock"]

[[components.api.artifacts]]
type = "docker"
ref  = "ghcr.io/foo/api:{version}"

[components.chart]
paths      = ["charts/myapp/**"]
bump_files = [{ file = "charts/myapp/Chart.yaml", key = "version" }]
changelog  = "charts/myapp/CHANGELOG.md"
depends_on = ["api"]

[[components.chart.artifacts]]
type = "helm"
ref  = "{component}-{version}.tgz"
```

A fully commented multi-component example lives at
[`examples/fastapi-helm/multicz.toml`](https://github.com/goabonga/multicz/blob/main/examples/fastapi-helm/multicz.toml).
