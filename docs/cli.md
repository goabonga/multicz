---
icon: lucide/terminal
---

# CLI

All commands are sub-commands of `multicz`. Run `multicz --help` or
`multicz <cmd> --help` for the typer-generated reference.

## `init`

Generate a `multicz.toml` tailored to the working tree.

```bash
multicz init                           # scan and write multicz.toml
multicz init --force                   # overwrite an existing file
multicz init --bare                    # generic single-component stub
multicz init --print                   # render to stdout, no file written
multicz init --print --bare            # generic stub to stdout
multicz init --detect                  # summary of what would be picked up
multicz init --detect --output json    # machine-readable detection
```

`--print` and `--detect` are non-destructive - safe to run inside CI.
`--detect` cannot combine with `--bare` or `--print`.

See [auto-discovery](concepts.md#auto-discovery) for the manifest
matrix.

## `status`

Brief table of pending bumps.

```bash
multicz status
multicz status --since origin/main     # PR preview
multicz status --since HEAD~10
```

`--since` accepts anything `git rev-parse` accepts: tags, branches,
SHAs, `HEAD~N`. See [choosing the commit window](#since).

## `plan`

Per-component plan with explicit reasons (commit / trigger / mirror /
manual).

```bash
multicz plan
multicz plan --output json
multicz plan --since origin/main
multicz plan --pre rc                  # plan as if invoked with bump --pre rc
multicz plan --finalize                # plan as if invoked with bump --finalize
multicz plan --force api:patch         # plan as if invoked with bump --force ...
multicz plan --summary $GITHUB_STEP_SUMMARY
```

JSON shape (truncated):

```json
{
  "schema_version": 1,
  "bumps": {
    "api": {
      "current_version": "1.2.0",
      "next_version": "1.3.0",
      "kind": "minor",
      "reasons": [
        {"kind": "commit", "sha": "abc1234", "type": "feat",
         "scope": "api", "subject": "add login flow",
         "files": ["src/auth.py"], "bump_kind": "minor"}
      ],
      "artifacts": [
        {"type": "docker", "ref": "ghcr.io/foo/api:1.3.0"}
      ]
    }
  }
}
```

Reason kinds: `commit`, `trigger`, `mirror`, `manual`.

## `explain`

Detailed breakdown of a single component, including which files of each
commit actually mapped to it.

```bash
multicz explain api
multicz explain api --since origin/main
```

Output (text):

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

Demotions from `bump_policy = "scoped"` show up here as
`Demoted from minor (bump_policy='scoped', different scope)`.

## `changed`

CI matrix gating. Lists components whose files changed since the given
reference.

```bash
multicz changed                        # per-component (vs each tag)
multicz changed --since origin/main    # every component vs main
multicz changed --output json
```

Default text output is one component name per line, pipeable into
shell loops. JSON output exposes both lists (`changed`,
`unchanged`) - ideal for `fromJson` in GitHub Actions matrices. See
the [CI matrix recipe](recipes.md#ci-matrix-gating).

Distinct from `plan`: `plan` says "would bump", `changed` says
"any activity, regardless of whether it's release-worthy". Release
commits matching `[project].release_commit_pattern` are filtered out.

## `bump`

Compute and apply the bump plan.

```bash
multicz bump                                   # write only
multicz bump --dry-run                         # plan, no writes
multicz bump --commit --tag                    # write, commit, tag
multicz bump --commit --tag --push             # …and push (--follow-tags)
multicz bump --component api --component web   # restrict to listed components
multicz bump --no-changelog                    # skip CHANGELOG.md updates
multicz bump --pre rc --commit --tag           # enter / continue an RC cycle
multicz bump --finalize --commit --tag         # drop the pre-release suffix
multicz bump --force api:patch                 # manual bump (rebuild)
multicz bump --force api:minor --force chart:major
multicz bump --commit -m "release: hotfix"     # verbatim message (no template)
multicz bump --sign                            # GPG-sign commit + tags
multicz bump --no-post-bump                    # skip post_bump shell hooks
multicz bump --output json                     # machine-readable
multicz bump --summary $GITHUB_STEP_SUMMARY    # markdown summary to file
```

Notable flags:

- `--commit` (`-C`) - stage written files and create a release commit
  using `[project].release_commit_message`. Together with `--commit-message` (`-m`),
  the verbatim string is used (no placeholders).
- `--tag` (`-t`) - create one annotated git tag per bumped component.
- `--push` - `git push --follow-tags`. Requires `--commit` or `--tag`
  to actually push something.
- `--sign` - equivalent to setting `[project].sign_commits = true` and
  `[project].sign_tags = true`. Either source enables signing; the CLI
  flag never disables.
- `--pre <label>` / `--finalize` - mutually exclusive. See [release
  candidates](recipes.md#release-candidates).
- `--force NAME:KIND` - repeatable. Bypasses commit detection. Validated
  upfront ([details](recipes.md#manual-bump)).
- `--no-post-bump` - skip
  [`post_bump`](configuration.md#post_bump) shell hooks for this run,
  even when `[project].post_bump_policy = "allow"`. When the policy is
  `"deny"` (default), hooks are already skipped - this flag silences
  the warning.

`bump` intentionally does **not** take `--since` - combining a custom
window with a write+tag can create tags that contradict actual history.

## `get`

Read a component's current version from the primary `bump_file`.

```bash
multicz get api
# 1.2.0
```

Convenient for CI shell scripts:

```bash
TAG=$(multicz get api)
docker build -t registry/myapp:$TAG .
```

Reserved sub-fields (e.g. `multicz get api.image_tag`) are not
implemented today - only `version` is exposed.

## `config`

Print the *effective* configuration: every default applied, every
alias normalised, every sparse override merged. Useful when an option
isn't behaving as you expected - `config` shows you what multicz
actually parsed, not what you typed.

```bash
multicz config                    # full config in TOML
multicz config -c api             # just one component (project still shown)
multicz config --output json      # machine-readable, pipe to jq
multicz config --source           # also print the loaded file path on stderr
```

What you see vs. what you wrote:

```toml
# in your multicz.toml:
[components.api]
paths      = ["src/**"]
bump_files = [{ file = "pyproject.toml", key = "project.version" }]

# `multicz config -c api` shows:
[project]
bump_rules = { feat = "minor", fix = "patch", perf = "patch", revert = "patch" }
overlap_policy   = "error"
post_bump_policy = "deny"
trigger_policy   = "patch"
# … every other default

[components.api]
paths         = ["src/**"]
exclude_paths = []
bump_policy   = "as-commit"
version_scheme = "semver"
# … every other default
[[components.api.bump_files]]
file = "pyproject.toml"
key  = "project.version"
```

Notable flags:

- `--output toml` (default) - round-trippable; you can copy the output
  back into a `multicz.toml` and it parses identically. Internally
  goes through Pydantic's JSON dump and strips `null` values (TOML
  has no null).
- `--output json` - mirrors the Pydantic schema with `Path` objects
  rendered as strings. Pipe to `jq` in CI to extract a specific
  field.
- `-c <name>` keeps the `[project]` table in the output (defaults are
  the most useful debugging context) and exactly one component.
- `--source` - writes the path of the loaded `multicz.toml` /
  `pyproject.toml` / `package.json` to **stderr**, so it doesn't
  pollute the JSON/TOML on stdout.

Common debugging checks:

| concern | look for |
|---|---|
| my `bump_rules` override isn't applied | `[project.bump_rules]` or `[components.X.bump_rules]` shows the resolved map; if a key is absent, the user table didn't reach Pydantic. |
| a writer isn't firing | `[[components.X.writers]]` array - check `type`, `file`, and that the entry survived schema validation. |
| `multicz` is reading the wrong file | run with `--source` to confirm which config path was discovered. |

## `graph`

Render the cascade DAG between components - the synoptic answer to
"if I bump X, what else bumps?". Two kinds of edges contribute, both
directed upstream → downstream:

- **mirrors** (file-based): A's mirror writes a path owned by B. Bumping
  A rewrites the file, which lands inside B's `paths`, which patch-bumps
  B (Helm chart `appVersion` is the canonical case).
- **depends_on** (name-based): B declares `depends_on = ["A"]`. Pure
  logical edge, no file written.

```bash
multicz graph                          # ASCII tree, all roots
multicz graph -c api                   # downstream cascade from api
multicz graph --output mermaid         # paste into a Markdown doc
multicz graph --output dot | dot -Tsvg # render via Graphviz
```

Sample tree on a `api / web / chart-api / chart-web / chart` umbrella:

```
api
└── chart-api (mirror charts/myapp-api/Chart.yaml:appVersion)
    └── chart (mirror charts/myapp/Chart.yaml:regex:- name: …)

web
└── chart-web (mirror charts/myapp-web/Chart.yaml:appVersion)
    └── chart (mirror charts/myapp/Chart.yaml:regex:- name: …)
```

Each tree root is a component with no incoming cascade edge. A DAG
sink reached from multiple roots (here: `chart`) is rendered under
*each* parent - the ASCII tree flattens the DAG by duplication so the
full propagation is visible at a glance. Cycles (forbidden by
`multicz validate`) get a `↻ cycle back to <name>` marker if they
slip through.

Notable flags:

- `--output tree` (default) - Rich-rendered ASCII tree; one root per
  pass, blank line between.
- `--output mermaid` - `graph LR` block ready for Markdown / GitHub
  PR descriptions / MkDocs. Edge labels are the same as the tree
  view (`mirror <file>:<key>` or `depends_on`).
- `--output dot` - Graphviz DOT for offline rendering. Pipe into
  `dot -Tsvg > graph.svg` or `dot -Tpng`.
- `-c <name>` filters to the *downstream* cascade rooted at `name`,
  for any of the three formats. Useful when scoping a review to a
  single component's blast radius.

Example PR-bot integration (renders the upcoming-release graph as a
Mermaid diagram on every push):

```bash
{
  echo '## Release cascade preview'
  echo
  echo '```mermaid'
  multicz graph --output mermaid
  echo '```'
} >> "$GITHUB_STEP_SUMMARY"
```

## `changelog`

Per-component log of conventional commits since the last tag.

```bash
multicz changelog                         # all components, plain text
multicz changelog -c api
multicz changelog --output md             # grouped Breaking / Features / Fixes / …
```

The grouping honours `[project].changelog_sections`,
`breaking_section_title`, `other_section_title`, and any commit type
set to `"none"` in `[project.bump_rules]`.

## `release-notes`

One-shot release notes for the upcoming bump or a past tag. No file is
written; the output IS the notes.

```bash
multicz release-notes api                 # upcoming bump for one component
multicz release-notes --all               # one block per bumping component
multicz release-notes --tag api-v1.3.0    # retrospective for a past tag
multicz release-notes --output json
```

Designed to pipe into `gh release create`:

```bash
gh release create api-v1.3.0 \
  --notes "$(multicz release-notes --tag api-v1.3.0)"
```

Stable release tags read commits since the previous *stable* tag (so
`v1.3.0` consolidates the whole RC cycle). Pre-release tags read
since the immediately previous tag (each RC shows only its delta).

Output formats:

- `md` (default) - sections (`### Features`, `### Fixes`, …)
- `text` - plain ASCII
- `json` - `{"sections": [...]}`

## `artifacts`

List the artifacts a component would publish at its current version.

```bash
multicz artifacts api
# api (1.2.0)
#   [docker] ghcr.io/foo/api:1.2.0
#   [docker] registry.acme.com/api:1.2.0

multicz artifacts api --version 1.4.0-rc.1
multicz artifacts --all --output json
```

`multicz` does not build or push artifacts itself - this surfaces the
rendered refs. The same data is embedded inside
`multicz plan --output json` and `multicz bump --output json` against
the planned/applied version.

## `plugins`

List every plugin discovered via the `multicz.plugins` entry-point
group, with its activation state and config section.

```bash
multicz plugins                   # text table
multicz plugins --output json
```

Three states are surfaced per plugin (`active`, `disabled`,
`inactive`) - see [Plugins → Activation](plugins.md#activation) for
the full model.

## `state`

Inspect the optional state file written after each bump.

```bash
multicz state                            # text
multicz state --output json
```

Exits non-zero if `[project].state_file` is not configured.

## `validate`

Run every config + repo sanity check. Recommended first step in CI.

```bash
multicz validate                  # exit 0 unless errors
multicz validate --strict         # also exit 2 on warnings
multicz validate --output json
```

Checks:

- `bump_files_exist`, `version_unreadable`
- `path_overlap` (governed by `overlap_policy`)
- `mirror_target_unowned` (info)
- `mirror_self_target` (warning)
- `mirror_cycle` (error)
- `trigger_cycle` (error)
- `changelog_not_a_file`
- `debian_changelog_missing`, `debian_changelog_unreadable`, `debian_changelog_unparseable`
- `state_drift`, `state_unknown_component` (when `state_file` is set)

Each finding prints a check identifier in parentheses, e.g.
`(bump_files_exist)`, so CI logs and PR comments can grep on it.

Exit codes: `0` = clean, `1` = at least one error, `2` = `--strict`
and at least one warning.

## `check`

Validate a commit message file against the conventional-commits regex.
Designed for the `commit-msg` git hook.

```bash
# .git/hooks/commit-msg
#!/bin/sh
exec multicz check "$1"
```

Read from stdin with `-`:

```bash
echo "feat: add login" | multicz check -
```

Restrict allowed types:

```bash
multicz check "$1" --type feat --type fix --type docs
```

Without `--type`, the allowed-types vocabulary is the union of the
conventional-commits default set and the keys of
[`[project.bump_rules]`](configuration.md#bump_rules) (loaded by
walking up from the current directory). This means a custom type
declared in your config - e.g. `infra = "patch"` - is accepted by the
hook without extra flags.

## `--since` { #since }

`status`, `plan`, `explain`, `changed` accept `--since` to override
the commit window:

| use case | command |
|---|---|
| PR preview | `multicz plan --since origin/main` |
| What changed in a branch | `multicz changed --since origin/main` |
| Inspect a specific point | `multicz status --since HEAD~10` |
| Migrate from a legacy global tag | `multicz plan --since v1.0.0` |
| Recover from removed/recreated tags | `multicz plan --since <known sha>` |

The override only moves the **commit window**. The "current version"
resolution (latest tag → primary `bump_file` → `initial_version`) is
unaffected, so PRs preview the "if merged" version without re-deriving
history. `bump` deliberately does not accept `--since`.

## Step-summary integration

`plan --summary <file>` and `bump --summary <file>` append a markdown
summary to `<file>`. Wire to `$GITHUB_STEP_SUMMARY` to surface a
release preview at the top of a workflow run page.

```yaml
- run: multicz plan --summary $GITHUB_STEP_SUMMARY
- run: multicz bump --commit --tag --summary $GITHUB_STEP_SUMMARY
```

The summary is written in addition to (not instead of) the regular
text/JSON output, so a single invocation can both populate the summary
and feed `jq` downstream.
