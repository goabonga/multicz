# Inline config in `package.json`

An npm-workspace monorepo where `multicz` reads its config from the
top-level `"multicz"` key inside `package.json` — no separate
`multicz.toml` file.

```
.
├── package.json          # workspaces + "multicz" config
├── packages/
│   ├── web/
│   │   └── package.json  # name = "web"
│   ├── mobile/
│   │   └── package.json  # name = "mobile"
│   └── shared/
│       └── package.json  # name = "shared"
```

The example uses the **array-of-tables** form for the components,
which translates naturally to JSON:

```json
{
  "multicz": {
    "components": [
      { "name": "web", "paths": ["packages/web/**"], ... },
      { "name": "mobile", "paths": ["packages/mobile/**"], ... }
    ]
  }
}
```

The dict-of-tables form also works:

```json
{
  "multicz": {
    "components": {
      "web": { "paths": ["packages/web/**"], ... },
      "mobile": { "paths": ["packages/mobile/**"], ... }
    }
  }
}
```

## What gets bumped

| commit touches | bump |
|---|---|
| `packages/web/src/App.tsx` (`feat:`) | `web` minor |
| `packages/mobile/index.tsx` (`fix:`) | `mobile` patch |
| `packages/shared/utils.ts` (`feat:`) | `shared` minor (the others stay put unless declared as `triggers`) |

Each workspace member gets its own tag (`web-v1.1.0`, `mobile-v0.5.1`,
`shared-v2.0.0`) and its own `CHANGELOG.md` next to its `package.json`.

## Cross-package triggers

If `web` and `mobile` both depend on `shared`, declare it explicitly:

```json
{
  "name": "web",
  "paths": ["packages/web/**"],
  "triggers": ["shared"]
}
```

Now any bump of `shared` cascades a patch into `web` and `mobile` too.

## Try it

```sh
cd examples/inline-package-json
multicz status
multicz bump --dry-run
```

`multicz` finds `"multicz"` inside `package.json` automatically — no
arguments needed.
