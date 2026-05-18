# Deprecation-policy plugin

A single Python package that opts into the built-in
[`plugins.deprecation`](../../src/multicz/plugins/builtin/deprecation/)
plugin. The plugin scans the sources for `@deprecated(since=..,
remove_in=..)` decorators (and `# DEPRECATED since=.. remove_in=..`
comments), then participates in three places along the release flow:

| where | what the plugin contributes |
|---|---|
| `multicz status` / `multicz plan` | one summary line per component: how many markers are newly *added*, *due for removal*, *upcoming* relative to the planned next version |
| `multicz bump` (gate) | a `post_plan` violation per marker whose `remove_in ≤ next` — the bump is aborted until the dead code is actually removed |
| `multicz changelog` / `release-notes` | adds a `Deprecated` section (markers landing in the release window) and a `Removed` section (markers whose deadline lines up with this release) |

```
.
├── multicz.toml          # config — declares [plugins.deprecation] to opt in
├── pyproject.toml        # [project].version = canonical api version (1.0.0)
└── src/legacy_api/
    ├── __init__.py
    ├── v1.py             # @deprecated(since="1.0.0", remove_in="2.0.0", …)
    └── v2.py             # # DEPRECATED since=1.2.0 remove_in=3.0.0 …
```

## The opt-in

The plugin ships with multicz but is **inactive** until the project
declares it. The minimum activation is two lines in `multicz.toml`:

```toml
[plugins.deprecation]
```

Confirm with `multicz plugins`:

```
┃ Plugin      ┃ Status ┃ Module                    ┃ Config section            ┃
│ deprecation │ active │ multicz.plugins.builtin.… │ [plugins.deprecation]     │
│             │        │                           │ scan=['src/**/*.py'],     │
│             │        │                           │ mode='error'              │
```

Without the section the same plugin would render as `inactive` — and
none of its hooks would run.

## Behaviour in the release flow

### 1. Minor / patch bump (no marker is due yet)

A `feat:` commit that touches the package proposes `1.0.0 → 1.1.0`. The
gate doesn't fire (no marker's `remove_in` ≤ `1.1.0`), but the status
line still surfaces the two pending deadlines so they don't get
forgotten:

```
┃ component ┃ current ┃ → ┃ next  ┃ kind  ┃ reasons                            ┃
│ api       │ 1.0.0   │ → │ 1.1.0 │ minor │ … feat(api): tweak v2 endpoint     │

  → deprecation: 2 upcoming
```

### 2. Major bump (marker becomes due)

A `feat!:` (or `BREAKING CHANGE:`) commit proposes `1.0.0 → 2.0.0`.
`v1.py`'s decorator says `remove_in="2.0.0"` — i.e. the dead code was
supposed to be gone before shipping `2.0.0`. The plugin emits an `error`
violation and the bump is **refused**:

```
┃ api       │ 1.0.0   │ → │ 2.0.0 │ major │ … feat(api)!: drop body kwarg …

  ✗ [api] deprecated since 1.0.0, must be removed by 2.0.0
      (planning 1.0.0 → 2.0.0) (from deprecation) (src/legacy_api/v1.py:26)

  → deprecation: 1 added, 1 due for removal, 1 upcoming
```

`multicz bump` exits with a non-zero status; CI fails. To unblock the
release, actually delete `old_endpoint` (and the decorator line that
flagged it) — then re-run `multicz bump`.

### 3. Changelog enrichment

After a successful bump, the rendered changelog gains plugin-owned
sections, merged in alongside the conventional-commit buckets:

```markdown
## api 2.0.0 (2026-05-18)

### Features
- drop body kwarg from v2 endpoint

### Removed
- `src/legacy_api/v1.py:26` (since 1.0.0, remove in 2.0.0) — use new_endpoint

### Deprecated
- `src/legacy_api/v2.py:14` (since 1.2.0, remove in 3.0.0) — body kwarg is going away, pass payload instead
```

The same sections appear in `multicz release-notes`, ready to ship to
GitHub Releases.

## Tweaks worth knowing

```toml
[plugins.deprecation]
# Default behaviour — fail the bump on a past-due marker.
mode = "error"

# Override the scan globs. When omitted, falls back to each component's
# own `paths`.
scan = ["src/**/*.py"]

# Different glob per component, when a single project mixes scan needs.
[plugins.deprecation.scan_per_component]
api = ["src/api/**/*.py"]
worker = ["src/worker/**/*.py"]

# Opt out temporarily without deleting the section.
# enabled = false
```

`mode = "warning"` keeps the violation visible in the CLI but lets the
bump proceed — useful when introducing the policy on an existing repo
and you need a grace period to clean up the historic markers.

## Try it

```sh
cd examples/deprecation-plugin
git init -q && git add -A && git commit -q -m "init"

# Plugin is listed as active because [plugins.deprecation] is declared.
multicz plugins

# Force a major bump so the past-due marker becomes a violation.
git commit --allow-empty -m "feat(api)!: drop v1"
multicz status                 # shows the advice line
multicz bump --dry-run         # aborts with the post_plan violation
```
