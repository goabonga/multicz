# CI workflow examples

Three drop-in pipelines wiring `multicz` into a release flow:

| platform | file |
|---|---|
| GitHub Actions | [`github-actions/release.yml`](github-actions/release.yml) |
| GitLab CI/CD | [`gitlab-ci.yml`](gitlab-ci.yml) |
| Azure Pipelines | [`azure-pipelines.yml`](azure-pipelines.yml) |

All three follow the same five-step flow:

1. **Validate** the multicz config (`multicz validate --strict`) — fail
   fast on misconfigured `bump_files`, mirror cycles, etc.
2. **Plan** (`multicz plan --output json`) and skip the rest when the
   plan is empty.
3. **Bump → commit → tag → push** in one shot
   (`multicz bump --commit --tag --push --output json`). The JSON
   payload is captured for downstream steps.
4. **Build & push artefacts** by filtering the JSON for the right type
   (`jq '.bumps[].artifacts[] | select(.type=="docker")'`).
5. (GitHub only) **Open a Release per new tag** with body from
   `multicz release-notes --tag <tag>`.

## Stable JSON shape

`multicz plan --output json` and `multicz bump --output json` both
include `schema_version: 1` so consumers can guard against breaking
changes:

```json
{
  "schema_version": 1,
  "bumps": {
    "api": {
      "current_version": "1.2.0",
      "next_version": "1.3.0",
      "kind": "minor",
      "reasons": [...],
      "artifacts": [
        {"type": "docker", "ref": "ghcr.io/foo/api:1.3.0"}
      ]
    }
  }
}
```

Common `jq` queries CI scripts can rely on:

```sh
# Will anything bump?
jq '.bumps | length > 0'

# Single component's next version
jq -r '.bumps.api.next_version'

# Every Docker ref to push
jq -r '.bumps[].artifacts[] | select(.type=="docker") | .ref'

# Tags freshly created (from bump output, after --tag)
jq -r '.git.tags[]'
```
