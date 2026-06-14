# Changelog

All notable changes to this component are documented here.

## [1.5.1] - 2026-06-14

### Fixes

- **release-notes**: surface cascade entries when rendering past tags (`a645a32`)

## [1.5.0] - 2026-06-14

### Features

- **changelog**: aggregated cross-component root CHANGELOG.md (`5c0544d`)

## [1.4.0] - 2026-06-14

### Features

- **cli**: propagate mirror + depends_on cascades through `multicz changed` (`993d504`)

## [1.3.0] - 2026-05-18

### Features

- **plugins**: add Plugin protocol + entry-point discovery registry (`23a1032`)
- **plugins**: wire post_plan hook in bump + accept [plugins.X] config sections (`2b4771e`)
- **cli**: surface plugin violations + status_lines in plan and status output (`3e0d483`)
- **plugins**: add built-in deprecation policy plugin (scanner + post_plan + enrich + status) (`249cd71`)
- **plugins**: plumb enrich_changelog into bump + release-notes (Deprecated/Removed sections) (`8717ac1`)
- **cli**: add 'multicz plugins' command to list discovered plugins + their config (`8175f5d`)

### Fixes

- **cli**: plugins command docstring — drop backticks + <name> mangled by Rich markup (`05a3454`)
- **plugins**: require explicit [plugins.<name>] section to activate a plugin (`e922b19`)
- **examples**: bump custom-plugin requires-python to >=3.12 to match multicz (`a97ded5`)
- **examples**: bump deprecation-plugin requires-python to >=3.12 to match multicz (`57186da`)
- **ci**: ruff cleanups + align copyright year with license-header check (`4a2fe18`)

## [1.2.1] - 2026-05-11

### Fixes

- **changelog**: render auto-buckets from bump_rules in render_body (`d0a7c9a`)

## [1.2.0] - 2026-05-10

### Features

- **changelog**: bucket bump_rules-driven types into auto sections (`13af3f7`)

## [1.1.0] - 2026-05-08

### Features

- **writers**: add `package` field to debian-changelog writer (`2a97080`)

## [1.0.0] - 2026-05-06

### Breaking changes

- **config**: switch trigger_policy default from match-upstream to patch (`6cfd541`)
- **security**: gate post_bump shell hooks behind post_bump_policy (`ff66cb2`)
- **config**: replace format='debian' with composable [[writers]] AOT (`01f7cdf`)
- **config**: drop deprecation aliases (ignored_types, triggers) for v1 (`6782fcb`)

### Features

- **init**: support --skip <ecosystems> to disable specific discovery strategies (`d3e9d5a`)
- **config**: make commit-type bump rules configurable, deprecate ignored_types (`d51492f`)
- **cli**: add `multicz config` to print the effective configuration (`d802536`)
- **cli**: add `multicz graph` to render the cascade DAG (`139b248`)

## [0.6.0] - 2026-05-04

### Features

- **config**: allow top-level changelog alongside debian.changelog (`437d8e1`)
- **cli**: write markdown changelog in debian bump path when configured (`4700bdd`)

### Fixes

- **debian**: filter changelog stanzas by changelog_sections like CHANGELOG.md (`b20b433`)

## [0.5.1] - 2026-05-04

### Fixes

- **cli**: include cascade entries in release-notes for upcoming bumps (`ab9dd9d`)

## [0.5.0] - 2026-05-04

### Features

- **config**: add Mirror schema with optional changelog_section and changelog_format (`bd87a37`)
- **changelog**: support per-cascade section and format overrides (`3deb283`)
- **cli**: wire mirror changelog overrides into cascade entries (`93ea982`)

## [0.4.0] - 2026-05-02

### Features

- **writers**: regex: prefix on bump_files key for arbitrary languages (`0c26457`)

## [0.3.0] - 2026-05-02

### Features

- **changelog**: render mirror/trigger cascades as Dependencies section (`4eab176`)

## [0.2.2] - 2026-05-01

### Fixes

- **bump**: post_bump progress goes to stderr (`677caa5`)

## [0.2.1] - 2026-05-01

### Fixes

- **bump**: detect post_bump file changes by content hash (`4b59b4e`)

## [0.2.0] - 2026-05-01

### Features

- **bump**: post_bump hooks regenerate lockfiles atomically (`4f43698`)

## [0.1.0] - 2026-05-01

### Features

- **config**: add multicz.toml schema with pydantic (`5bf0dd5`)
- **commits**: parse conventional commits since last tag (`97a3d64`)
- **components**: match changed files via gitignore-style globs (`c62e200`)
- **planner**: build bump plan with trigger and mirror cascades (`bf13e36`)
- **writers**: edit TOML and YAML version fields in place (`0424802`)
- **cli**: add typer CLI with init, status, bump, get, changelog (`68f2727`)
- **writers**: support package.json via the json module (`769da4c`)
- **cli**: commit and tag bumped versions in one shot (`edb3610`)
- **cli**: emit per-component markdown changelog (`5b4d33b`)
- **cli**: add check command for commit-msg git hooks (`589dfe8`)
- **changelog**: per-component CHANGELOG.md rendering (`9d66492`)
- **cli**: write CHANGELOG.md during bump (`16c4798`)
- **discovery**: scan repo manifests to seed components (`f5e41b9`)
- **cli**: auto-discover components on init, add --bare for stub (`91d1c76`)
- **changelog**: support configurable sections per project (`be4ce0f`)
- **discovery**: support multiple charts with name-aware mirror wiring (`e37c743`)
- **writers**: support .properties files for JVM/gradle stacks (`289b16a`)
- **discovery**: detect Rust crates and Cargo workspaces (`5e8cc70`)
- **discovery**: detect Go modules with tag-driven versioning (`63540d5`)
- **discovery**: detect Gradle projects via gradle.properties (`006495b`)
- **discovery**: expand npm/yarn/pnpm workspaces (`f48e38d`)
- **discovery**: support uv workspaces and Poetry projects (`df9d516`)
- **discovery**: scan package.json recursively when no workspace declared (`c7da6f6`)
- **config**: accept [[components]] array-of-tables syntax (`d1de39e`)
- **debian**: parse, render, and prepend debian/changelog stanzas (`b7b8a1c`)
- **cli**: bump debian-format components by prepending a stanza (`9971d76`)
- **discovery**: detect debian/changelog packages (`0966454`)
- **planner+cli**: support --pre release-candidate cycles (`8a47756`)
- **changelog**: configurable finalize strategy (`7196b56`)
- **config**: read multicz config from pyproject.toml or package.json (`53a303c`)
- **config**: per-component tag_format with prefix-collision check (`22fe559`)
- **cli**: add plan and explain commands (`f8e25c9`)
- **cli**: add validate command (`ebbc897`)
- **config**: explicit overlap_policy for shared-path ownership (`cfba4dd`)
- **planner**: per-component bump_policy with scoped demotion (`a83a9e7`)
- **config**: ignored_types to fully filter commit types from bumps and changelog (`0a4fe11`)
- **cli**: add release-notes command (`24f4cb1`)
- **planner**: per-component version_scheme (semver vs pep440) (`ad4f500`)
- **config**: add artifacts to surface what CI should build and push (`014a51b`)
- **cli**: add changed command for CI matrix gating (`68c8e36`)
- **planner**: expose --since on status/plan/explain (`529f923`)
- **state**: optional state file with drift detection (`e8dd52f`)
- **discovery**: honor [workspace].exclude (Cargo) and !pattern (npm) (`d95d7c9`)
- **cli**: add --print and --detect to init (`f752e11`)
- **planner**: unknown_commit_policy controls non-conventional commits (`9bdf5f5`)
- **commits**: map revert to patch and surface in default Reverts section (`75033cb`)
- **cli**: customizable release commit message template (`9ea0eb1`)
- **cli**: force-bump components without commits via --force (`102a097`)
- **cli**: stable schema_version on plan/bump JSON; rename next->next_version (`a97e3af`)
- **cli**: signed commits and tags via --sign and [project] config (`0d2b840`)
- **config**: validate component names against safe regex (`11b96a6`)
- **config**: depends_on alias and trigger_policy for dependency cascades (`0384041`)
- **cli**: --summary flag for GitHub step summary integration (`61d651a`)

### Fixes

- **components**: use modern 'gitignore' pathspec factory (`00fd82c`)
- **planner**: fall back to bump_file value when no tag exists (`17ecb19`)
- **discovery**: drop .dockerignore from auto-discovered paths (`70e77e4`)
