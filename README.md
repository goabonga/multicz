<h1 align="center">
  <img src="https://github.com/goabonga/multicz/raw/main/docs/multicz.svg" alt="multicz" width="120" /><br/>
  multicz
</h1>

<p align="center">
  <em>Multi-component versioning for monorepos.</em>
</p>

<p align="center">
  <a href="https://github.com/goabonga/multicz/actions/workflows/ci.yml"><img src="https://github.com/goabonga/multicz/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"/></a>
  <a href="https://codecov.io/gh/goabonga/multicz"><img src="https://img.shields.io/codecov/c/github/goabonga/multicz?logo=codecov" alt="Codecov"/></a>
  <a href="https://github.com/goabonga/multicz/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"/></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python"/></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"/></a>
</p>

**multicz** bumps a Python app, its Docker image, and the Helm chart that
deploys it from a single conventional-commit history - each with its own
version line and its own git tag. Declare the components of a monorepo in
`multicz.toml`, and it plans the bumps, writes the version files and the
changelogs, then commits and tags.

<p align="center">
  <img src="https://github.com/goabonga/multicz/raw/main/docs/demo.gif" alt="multicz demo" width="720">
</p>

## Documentation

The project site is published from `main` to GitHub Pages:
<https://goabonga.github.io/multicz/>.

- [Get started](https://goabonga.github.io/multicz/get-started/) - install, minimal config, first bump
- [Concepts](https://goabonga.github.io/multicz/concepts/) - components, mirrors, triggers, cascades, bump policies
- [Configuration](https://goabonga.github.io/multicz/configuration/) - full `multicz.toml` reference
- [CLI](https://goabonga.github.io/multicz/cli/) - every command and flag
- [Plugins](https://goabonga.github.io/multicz/plugins/) - the plugin protocol and the built-in plugins
- [Recipes](https://goabonga.github.io/multicz/recipes/) - FastAPI + Helm walkthrough, CI matrix gating, release candidates
- [Why multicz?](https://goabonga.github.io/multicz/why/) - vs. semantic-release, Commitizen, Changesets, bump-my-version
- [Security](https://goabonga.github.io/multicz/security/) - guarantees and CI hardening

## Requirements

- Python 3.12+
- `git`

## Installation

```bash
pip install multicz
```

Or run it without installing, using [uv](https://docs.astral.sh/uv/):

```bash
uv tool install multicz   # or: pipx install multicz
uvx multicz --help
```

## Usage

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
related versions. See the
[configuration reference](https://goabonga.github.io/multicz/configuration/)
for every option.

- **Per-component versions** - each component has its own version line and
  its own git tag (`api-v1.2.0`, `chart-v0.5.0`).
- **Conventional-commit driven** - `feat:` → minor, `fix:` → patch,
  `BREAKING CHANGE:` → major. Scopes route the bump to the right component.
- **Mirrors and triggers** - bump api `1.2.0` → `1.3.0` and the Helm chart's
  `appVersion` follows; the chart's own version cascades a patch.
- **No network, no auto-updates.** Pure `git` + filesystem. Same input yields
  the same plan byte-for-byte.

## Development

```bash
git clone https://github.com/goabonga/multicz.git
cd multicz
uv sync

# Quality gates (mirrored in CI).
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src
uv run pyright
uv run pytest --cov=multicz

# Install the pre-commit + commit-msg hooks.
uv run pre-commit install
```

## Versioning and release

multicz versions itself. Every push to `main` runs
`multicz bump --commit --tag --push` - driven by
[Conventional Commits](https://www.conventionalcommits.org/) - then
publishes to PyPI and deploys the docs.

```bash
# Preview the next release against the current branch.
uv run multicz status
```

## Contributing

See [CONTRIBUTING.md](https://github.com/goabonga/multicz/blob/main/CONTRIBUTING.md)
for the workflow, the branch and commit-message conventions, and the
test/lint expectations. By participating you agree to the
[Code of Conduct](https://github.com/goabonga/multicz/blob/main/CODE_OF_CONDUCT.md).

Security issues: please follow the disclosure process in
[SECURITY.md](https://github.com/goabonga/multicz/blob/main/.github/SECURITY.md).

## License

Distributed under the
[MIT License](https://github.com/goabonga/multicz/blob/main/LICENSE).
