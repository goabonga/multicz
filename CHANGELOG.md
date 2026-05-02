# Changelog

All notable changes to this component are documented here.

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
