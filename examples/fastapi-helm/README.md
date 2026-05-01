# FastAPI service + Helm chart

A Python web service shipped together with the Helm chart that deploys
it. The two pieces have **independent versions**, but the chart's
`appVersion` always tracks the API version (1:1 mirror) and a chart
release is implicitly cut whenever the API version moves.

```
.
├── multicz.toml          # dedicated config
├── pyproject.toml        # [project].version = canonical api version
├── src/                  # FastAPI sources
├── tests/
├── Dockerfile            # container build (artifact of the api)
└── charts/myapp/
    ├── Chart.yaml        # version (chart) + appVersion (mirror of api)
    ├── templates/        # kubernetes manifests
    └── values.yaml
```

## What gets bumped, when

| commit touches | api | image tag | chart.version | Chart.yaml appVersion |
|---|---|---|---|---|
| `src/main.py` (`feat:`) | minor (e.g. 1.3.0) | follows api (`1.3.0`) | patch (cascade) | mirror (`1.3.0`) |
| `Dockerfile` (`fix:` for a CVE) | patch | follows api | patch (cascade) | mirror |
| `charts/myapp/templates/*.yaml` | — | — | patch | — |
| `charts/myapp/values.yaml` (config) | — | — | patch | — |

Two key invariants drive this layout:

* **Image tag = api version.** The Docker image is rebuilt whenever
  `api` bumps; you read its tag from CI as `multicz get api`. There's
  no separate `image` component because the image is just a build
  artifact of `api`.
* **Helm chart immutability.** `chart-0.5.0` always pins exactly one
  `appVersion`. Any time the mirror writes a new `appVersion` into
  `Chart.yaml`, the chart's own `version` cascades a patch — so two
  pulls of the same chart-X.Y.Z tarball are guaranteed to be
  byte-identical.

## Try it

```sh
cd examples/fastapi-helm
multicz status
multicz bump --dry-run
```

`multicz` finds the dedicated `multicz.toml` next to `pyproject.toml`.
The same setup also works inlined under `[tool.multicz]` inside
`pyproject.toml` if you prefer one fewer file at the repo root — see
[`../inline-pyproject/`](../inline-pyproject/).

## Release flow in CI

```yaml
- run: |
    multicz bump --commit --tag --push
    TAG=$(multicz get api)
    docker build -t registry/myapp:$TAG .
    docker push registry/myapp:$TAG
    helm package charts/myapp
    helm push myapp-*.tgz oci://registry/charts
```

A single command writes both `pyproject.toml` and `charts/myapp/Chart.yaml`,
creates one release commit, and produces two annotated tags
(`api-vX.Y.Z` + `chart-vA.B.C`) pointing at the same SHA.
