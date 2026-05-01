# multicz examples

Each subdirectory shows a different way to set up `multicz`.

| directory | scenario | config lives in |
|---|---|---|
| [`fastapi-helm/`](fastapi-helm/) | Python API + Helm chart with `appVersion` mirror cascade | `multicz.toml` (dedicated) |
| [`inline-pyproject/`](inline-pyproject/) | FastAPI backend + React SPA, no separate config file | `pyproject.toml` `[tool.multicz]` |
| [`inline-package-json/`](inline-package-json/) | npm-workspace monorepo (`web`, `mobile`, `shared`) | `package.json` `"multicz"` key |

Search order at every directory level (walked up from `cwd`):

1. `multicz.toml` — always wins when present
2. `pyproject.toml` with `[tool.multicz]`
3. `package.json` with a `"multicz"` key
