# go-deps plugin

A worked example of the `Plugin.affects` hook: claim a Go component
for a changed file using `go list -deps` - the compiler's own import
graph - instead of relying solely on a hand-maintained `paths` glob.

```
.
├── multicz.toml                        # opts the plugin in
├── pyproject.toml                      # packages go_deps_plugin + registers the entry-point
├── go.mod
├── cmd/
│   ├── api/{main.go,version.txt}       # component "api"
│   └── worker/{main.go,version.txt}    # component "worker"
└── internal/
    ├── auth/auth.go                    # imported by cmd/api only
    └── queue/queue.go                  # imported by cmd/worker only
```

## The problem

`multicz.toml` here declares:

```toml
[components.api]
paths = ["cmd/api/**"]

[components.worker]
paths = ["cmd/worker/**"]
```

That's the realistic state most Go monorepo configs end up in: `cmd/`
is easy to remember, `internal/` is not. A change to
`internal/auth/auth.go` - which `cmd/api/main.go` imports - doesn't
match `cmd/api/**`, so plain path matching says `api` is unaffected.
It's wrong: `go build ./cmd/api` picks up that file every time.

## The fix

```toml
[plugins.go-deps]
[plugins.go-deps.packages]
api = "./cmd/api"
worker = "./cmd/worker"
```

`affects(ctx, component, paths)` only runs when path matching has
*already* failed to claim `component` for a given change (see
[`docs/plugins.md`](../../docs/plugins.md#affects)). When it does run
here, it resolves `go list -deps -f '{{.Dir}}' ./cmd/api`, gets back
every directory `cmd/api`'s binary actually imports (including
`internal/auth`), and checks whether any of the changed paths live
under one of them.

## Try it

```sh
cd examples/go-deps-plugin
pip install -e .        # registers the entry point
git init -q && git add -A && git commit -q -m "chore: init"
```

Change only `internal/auth/auth.go` and commit it:

```sh
sed -i 's/"token"/"token-v2"/' internal/auth/auth.go
git commit -qam "fix: rotate token format"
```

Without the plugin (`[plugins.go-deps]` commented out), `api` looks
unaffected:

```sh
$ multicz changed --since HEAD~1 --output json
{"changed": [], "unchanged": ["api", "worker"]}
```

With it active, `api` is correctly claimed - and `worker`, which
never imports `internal/auth`, correctly is not:

```sh
$ multicz changed --since HEAD~1 --output json
{"changed": ["api"], "unchanged": ["worker"]}
```

## Talking points if you adapt this plugin

- **`affects` is a fallback, not a replacement.** It's only ever
  consulted once `paths` matching has already missed - a change
  inside `cmd/api/**` never reaches the plugin at all, so `go list`
  only runs for the changes that actually need the extra look.
- **One `go list` call per (repo, package) per run.** The plugin
  caches resolved dependency directories on `self` for the lifetime
  of the process - `changed` calls `affects` once per component (with
  all changed paths batched), and the planner calls it once per
  (component, commit) pair, so without caching a large history would
  shell out to `go` once per commit.
- **A broken toolchain degrades to "no opinion".** If `go` isn't on
  `PATH`, or the package doesn't build, `_dep_dirs` returns an empty
  set and `affects` returns `False` - the bump still proceeds on
  whatever `paths` alone could determine, it just loses the extra
  coverage.
- **Unconfigured components are untouched.** A component absent from
  `[plugins.go-deps.packages]` gets `False` immediately - this plugin
  never guesses at an import path on your behalf.
- **Same idea generalizes past Go.** Any ecosystem with an
  authoritative, queryable dependency graph (`cargo tree`, `go list`,
  a language server's reverse-dependency index) can back an `affects`
  implementation the same way - the `OwnershipContext` the hook
  receives carries nothing Go-specific.

## Distributing the plugin for real

For a plugin you publish to PyPI, the only differences from this
example are cosmetic:

- The `pyproject.toml` typically declares a tighter `multicz` version
  range matching the Plugin Protocol you tested against
  (`multicz>=1.2,<2`).
- `pip install your-plugin` makes the entry point available in any
  env that already has multicz; the consumer then adds
  `[plugins.go-deps]` to their `multicz.toml` to opt in.
