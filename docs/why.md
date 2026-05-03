---
icon: lucide/git-compare
---

# Why multicz?

Multicz isn't trying to replace
[`semantic-release`](https://github.com/semantic-release/semantic-release),
[Commitizen](https://commitizen-tools.github.io/commitizen/),
[Changesets](https://github.com/changesets/changesets), or
[`bump-my-version`](https://github.com/callowayproject/bump-my-version)
— they're better than multicz at what they're designed for. Multicz
exists because none of them cleanly modelled the same shape of
repository: multiple deliverables, mirrors between them, commits
driving bumps without writing release notes by hand.

## Comparison

### `semantic-release`

Excellent for a single-package repo (one `package.json`, one release
stream, one tag scheme). Multi-package support exists via plugins
(`semantic-release-monorepo`, `semantic-release-plus`) but feels
grafted on, and the workflow centres on auto-publishing to a registry.

Multicz takes the opposite stance: components are first-class, and
publishing is left to CI.

### Commitizen

Has two faces — `cz commit` (interactive wizard for writing
conventional commits) and `cz bump` (semver bumper). Multicz cares
about the second; for the first, use `cz commit` *or*
[`multicz check`](cli.md#check) as a `commit-msg` hook.

`cz bump` itself is single-version: one `pyproject.toml`, one
`[tool.commitizen]` block, one tag.

### Changesets

The state of the art for JS monorepos: each PR adds a "changeset" file
declaring the intended bump, and the release tool aggregates them.
That model excels when the team writes the changeset by hand — the
intent is encoded explicitly, not inferred from commits.

It's less natural when you also have a Helm chart that should mirror
the API version automatically, a `.deb` source package, or a Cargo
workspace member.

### `bump-my-version`

Successor to `bump2version`. Great for the "many files, one version"
problem: pattern-based replacements across version strings that need
to stay in sync. It doesn't read commits — you tell it the bump kind
explicitly. Multicz keeps the multi-file substitution and adds commit
detection plus per-component independence.

### Other related tools

`release-please`, `poetry-bumpversion`, `knope`, `cargo-release`,
`hatch version` — each solves a slice of the problem. None I tried can
express *"a commit touching `src/` bumps `api` minor; the chart
cascades a patch because its `appVersion` mirrors api"* in a single
config without scripting around the tool.

## What multicz does differently

- **Components, not packages.** Everything is keyed by component name
  (`api`, `chart`, `frontend`). A component can be backed by any
  manifest — `pyproject.toml`, `Chart.yaml`, `package.json`,
  `Cargo.toml`, `go.mod`, `gradle.properties`, `debian/changelog` —
  or none at all (tag-driven Go modules).
- **File ownership via globs.** `paths = ["src/**", "Dockerfile"]`
  declares what a component owns, gitignore-style. Multiple components
  can share or exclude paths via
  [`overlap_policy`](concepts.md#overlap-policy).
- **Mirrors with cascade semantics.** A
  [mirror](concepts.md#mirrors) writes a component's version into
  another component's file (the canonical case: api version → Helm
  chart's `appVersion`). The receiving component cascades a patch bump
  so the chart pins exactly one app version per release.
- **No publishing.** Multicz never pushes images, packages a chart,
  or uploads to a registry. It tells CI *what* changed, *what version*
  to use, and *what artefacts to publish*; CI does the work.
- **Multi-format substitution.** TOML, YAML, JSON, `.properties` and
  plain files are all supported with formatting preserved (comments,
  key order, quote style). A
  [regex escape hatch](concepts.md#regex-escape-hatch) covers
  everything else.
- **Stateless by default.** Every command re-derives from git tags
  and the in-tree manifests. The optional
  [state file](concepts.md#optional-state-file) is for teams that want
  an audit trail and drift detection.

## When you should reach for something else

- You have a single Python package and want a one-command bumper →
  `bump-my-version`, `cz bump`, or `hatch version`.
- You have a JS monorepo and your team is happy writing changesets
  by hand → `changesets` is more battle-tested.
- You have one repo per package and want auto-publish on every
  release → `semantic-release` + its release plugin.
- You don't want any commit grammar at all → `bump-my-version` (you
  drive the kind manually).

If your repo has multiple deliverables, mirrors between them, and you
want commits to drive the bumps without writing release notes by hand
— that's the case multicz exists for.
