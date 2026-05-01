# Inline config in `pyproject.toml`

A FastAPI backend + React SPA monorepo where `multicz` reads its config
from `[tool.multicz]` inside the existing `pyproject.toml` — no
separate `multicz.toml` file.

```
.
├── pyproject.toml        # backend manifest + multicz config
├── src/                  # FastAPI sources
├── tests/
├── Dockerfile
└── frontend/
    ├── package.json      # name = "web", version = "0.5.0"
    └── src/
```

## What gets bumped

| commit touches | bump |
|---|---|
| `src/main.py` (`feat:`) | `api` minor |
| `Dockerfile` (`fix:`) | `api` patch |
| `frontend/src/App.tsx` (`feat:`) | `web` minor |

Each component gets its own tag (`api-v1.1.0`, `web-v0.6.0`) and its
own `CHANGELOG.md` (root for api, `frontend/CHANGELOG.md` for web).

## Try it

```sh
cd examples/inline-pyproject
multicz status
multicz bump --dry-run
```

`multicz` finds `[tool.multicz]` in `pyproject.toml` automatically — no
arguments needed.
