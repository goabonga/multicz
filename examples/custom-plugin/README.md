# Custom plugin — `newsy`

A worked example of writing your own multicz plugin. `newsy` is a
towncrier-flavoured news-fragment plugin: every change drops a small
Markdown file under `changes.d/<id>.<type>.md`, and at release time
those files become changelog sections grouped by `<type>`.

```
.
├── multicz.toml              # opts the plugin in
├── pyproject.toml            # packages newsy + registers the entry-point
├── changes.d/
│   ├── 0001.feat.md
│   ├── 0002.fix.md
│   └── 0003.chore.md
└── src/
    ├── newsy/__init__.py     # the plugin (this is what you'd ship)
    └── app/__init__.py       # the component being versioned
```

The plugin exercises every hook of the multicz Plugin Protocol — read
[`src/newsy/__init__.py`](src/newsy/__init__.py) alongside this
walkthrough.

## Anatomy of a plugin

A plugin is **a Python package that registers under the
`multicz.plugins` entry-point group**. multicz discovers it the same
way for built-in and third-party plugins; there is no privileged
loader path.

```toml
# pyproject.toml
[project]
name = "newsy"
dependencies = ["multicz"]

[project.entry-points."multicz.plugins"]
newsy = "newsy:NewsyPlugin"   # key = plugin name, value = "module:ClassName"
```

The class implements the Protocol — easiest path is to subclass
`BasePlugin`, which provides no-op defaults so you only override the
hooks you care about:

```python
from multicz.plugins import BasePlugin, ChangelogEntry, Severity, Violation

class NewsyPlugin(BasePlugin):
    name = "newsy"

    def post_plan(self, ctx) -> list[Violation]: ...
    def enrich_changelog(self, ctx, component) -> list[ChangelogEntry]: ...
    def status_lines(self, ctx) -> list[str]: ...
```

The `ctx` object passed to every hook carries:

| field | content |
|---|---|
| `ctx.config` | the parsed multicz config (whole file — read other sections if you need them) |
| `ctx.repo` | absolute `Path` to the repository root |
| `ctx.plan` | the `Plan` multicz computed (`ctx.plan.bumps[component]` for each `PlannedBump`) |
| `ctx.plugin_config` | **only** the `[plugins.<name>]` slice of the user's config, defaulted to `{}` if absent |

## Install + opt-in

For this example the plugin lives in the same checkout as multicz, so
an editable install is the quickest way to make it visible:

```sh
cd examples/custom-plugin
pip install -e .        # registers the entry point
```

Then declare `[plugins.newsy]` in `multicz.toml` (already done here)
and confirm:

```
$ multicz plugins
┃ Plugin │ Status │ Module │ Config section
│ newsy  │ active │ newsy  │ [plugins.newsy] directory='changes.d', …
```

Without that section the plugin renders as `inactive` and none of its
hooks run — explicit opt-in, same as built-in plugins.

## Behaviour in the release flow

### 1. With fragments — status + enriched changelog

A `feat:` commit proposes `0.1.0 → 0.2.0`. The status line reports the
fragment inventory:

```
┃ component ┃ current ┃ → ┃ next  ┃ kind  ┃ reasons                            ┃
│ app       │ 0.1.0   │ → │ 0.2.0 │ minor │ … feat(app): stream responses …    │

  → newsy: 3 fragments (1 chore, 1 feat, 1 fix)
```

`multicz release-notes app` then renders the fragments as sections,
side-by-side with the conventional-commit bullets:

```markdown
### Features
- **app**: stream responses line-by-line (`8bafd47`)
- Streaming responses are now flushed line-by-line instead of buffered to EOF — long-running endpoints feel responsive again.

### Fixes
- Stopped logging the session token in the request-id header tap.

### Misc
- Migrated CI to the shared workflow library, dropping ~200 lines of copy-pasted YAML.
```

### 2. With zero fragments — gate

Remove `changes.d/` (or empty it) and the `post_plan` hook refuses the
bump:

```
$ multicz bump --dry-run
  ✗ no changelog fragments under changes.d/ — add at least one
    <id>.<type>.md file or set ``require_fragment_for_bump = false``
    under [plugins.newsy] (from newsy)
```

`multicz bump` exits with a non-zero status; CI fails. The fix is
either to add a fragment or to relax the gate by setting
`require_fragment_for_bump = false`.

## Talking points if you adapt this plugin

* **`post_plan` returns `Violation`s, never raises.** Plugins that
  raise are caught by the runner, logged as a `RuntimeWarning`, and
  treated as if they returned `[]`. Use `Severity.error` to abort the
  bump, `warning` to flag without blocking, `info` for purely
  informational annotations.
* **`enrich_changelog` is called per-component.** Sections you return
  are merged into the rendered changelog under their `section` title
  — so two plugins that both return a `"Removed"` section coalesce
  cleanly into one bucket. The same return value is reused for
  `multicz release-notes`.
* **`status_lines` is text-only.** It's printed verbatim after the
  bump table in `multicz status` / `multicz plan`. Rich markup is
  supported (`[bold]`, `[red]`, etc.) — escape literal brackets with
  `\[` if you mean them literally.
* **Config defaults belong to the plugin.** multicz only injects the
  raw `[plugins.<name>]` dict; defaulting and validation are entirely
  the plugin's responsibility. The minimal opt-in is an empty
  `[plugins.newsy]` section.
* **`name` is the contract.** It must match the entry-point key in
  `pyproject.toml` *and* the TOML section a consumer writes in their
  `multicz.toml`. Pick something short, kebab-case, namespace-y if
  you might collide.

## Distributing the plugin for real

For a plugin you publish to PyPI, the only differences from this
example are cosmetic:

* The `pyproject.toml` typically declares a tighter `multicz` version
  range matching the Plugin Protocol you tested against
  (`multicz>=1.2,<2`).
* The package ships *only* the plugin code (no `app/` stand-in).
* `pip install your-plugin` makes the entry point available in any
  env that already has multicz; the consumer then adds
  `[plugins.<name>]` to their `multicz.toml` to opt in.
