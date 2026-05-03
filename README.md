# multicz

Multi-component versioning for monorepos. Bump a Python app, its Docker image,
and the Helm chart that deploys it from a single conventional-commit history —
each with its own version line and its own git tag.

<p align="center">
  <img src="https://github.com/goabonga/multicz/raw/main/docs/demo.gif" alt="multicz demo" width="720">
</p>

## Install

```bash
uv tool install multicz   # or: pipx install multicz / pip install multicz
```

## Quickstart

```bash
# 1. scaffold a multicz.toml in the repo root
multicz init

# 2. see what would bump from the current commit window
multicz changed
multicz explain api

# 3. apply the bump (writes version files + changelog, commits, tags)
multicz bump --commit --tag

# 4. ship it
git push --follow-tags
```

For multi-component setups (api + chart, app + image + helm, ...), declare
each component's paths in `multicz.toml` and let mirrors and triggers cascade
related versions. See the [docs](https://goabonga.github.io/multicz/) for the
full configuration reference.

## What it does

- **Per-component versions** — each component has its own version line and
  its own git tag (`api-v1.2.0`, `chart-v0.5.0`).
- **Conventional-commit driven** — `feat:` → minor, `fix:` → patch,
  `BREAKING CHANGE:` → major. Scopes route the bump to the right component.
- **Mirrors and triggers** — bump api `1.2.0` → `1.3.0` and the Helm chart's
  `appVersion` follows; the chart's own version cascades a patch.
- **No network, no auto-updates.** Pure `git` + filesystem. Same input yields
  the same plan byte-for-byte.

## Documentation

Published at **<https://goabonga.github.io/multicz/>**:

- [Get started](https://goabonga.github.io/multicz/get-started/) — install, minimal config, first bump
- [Concepts](https://goabonga.github.io/multicz/concepts/) — components, mirrors, triggers, cascades, bump policies
- [Configuration](https://goabonga.github.io/multicz/configuration/) — full `multicz.toml` reference
- [CLI](https://goabonga.github.io/multicz/cli/) — every command and flag
- [Recipes](https://goabonga.github.io/multicz/recipes/) — FastAPI + Helm walkthrough, CI matrix gating, release candidates
- [Why multicz?](https://goabonga.github.io/multicz/why/) — vs. semantic-release, Commitizen, Changesets, bump-my-version
- [Security](https://goabonga.github.io/multicz/security/) — guarantees and CI hardening

## License

[MIT](https://github.com/goabonga/multicz/blob/main/LICENSE)
