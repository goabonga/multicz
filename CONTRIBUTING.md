# Contributing to multicz

Thanks for taking the time to contribute. This guide covers the setup,
development loop, and the conventions multicz uses for branches and
commits — both of which drive the project's own release pipeline.

## Setup

multicz is a Python 3.12+ project managed with [uv](https://docs.astral.sh/uv/).

```bash
# 1. install uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. clone and sync
git clone https://github.com/goabonga/multicz
cd multicz
uv sync

# 3. run the CLI from source
uv run multicz --help
```

`uv sync` installs the runtime plus the `dev` group (pytest, pytest-cov,
ruff) into `.venv/`. Add `--group docs` to also install Zensical for the
documentation site.

## Development workflow

### Tests

```bash
uv run pytest                              # full suite
uv run pytest tests/test_bump.py           # one file
uv run pytest -k cascade                   # filter by name
uv run pytest --cov=multicz                # with coverage
```

Test config lives in `[tool.pytest.ini_options]` (`pyproject.toml`):
`testpaths = ["tests"]` and `-q` by default.

### Lint and format

multicz uses [ruff](https://docs.astral.sh/ruff/) for both linting and
formatting. Config is in `[tool.ruff.lint]` (`pyproject.toml`).

```bash
uv run ruff check                # lint
uv run ruff check --fix          # auto-fix what's safe
uv run ruff format               # format
uv run ruff format --check       # CI-style check (no writes)
```

Selected rule set: `E F I B UP SIM N RUF`. Line length is 100.

### Documentation site (optional)

```bash
uv sync --group docs
uv run zensical serve            # http://localhost:8000
uv run zensical build --strict   # validate links + render
```

The doc site is the user-facing source of truth — when you change
behavior, update the relevant page under `docs/`.

## Branch naming

Use `<type>/<kebab-description>`, where `<type>` matches the conventional
commit type the work will produce:

| type        | example                                |
|-------------|----------------------------------------|
| `feat/`     | `feat/cli-changed-json-output`         |
| `fix/`      | `fix/bump-empty-release-exit-code`     |
| `docs/`     | `docs/concepts-mirrors-clarify`        |
| `refactor/` | `refactor/writers-regex-prefix`        |
| `chore/`    | `chore/uv-lock-bump`                   |
| `ci/`       | `ci/cache-uv-deps`                     |
| `test/`     | `test/cover-trigger-cycles`            |

Avoid `wip`, `tmp`, or personal-name-only branches.

## Commit messages

multicz uses [Conventional Commits](https://www.conventionalcommits.org/)
because its own release pipeline reads them:

```
<type>(<optional-scope>): <imperative summary>

<optional body explaining the why>

<optional footer — BREAKING CHANGE: ..., refs, etc.>
```

How commit types map to releases (multicz uses itself for versioning):

| prefix                                      | bump  |
|---------------------------------------------|-------|
| `fix:`, `perf:`                             | patch |
| `feat:`                                     | minor |
| any commit with `BREAKING CHANGE:` in body, or `feat!:` / `fix!:` | major |
| `docs:`, `chore:`, `refactor:`, `test:`, `style:`, `ci:`, `build:` | none  |

Examples from this repo's history:

```
feat(writers): regex: prefix on bump_files key for arbitrary languages
fix(bump): post_bump progress goes to stderr
docs(readme): slim to cover page, link to published doc site
chore(release): bump multicz 0.2.2 -> 0.3.0
```

Guidelines:

- **One logical change per commit.** A bug fix and a refactor are two
  commits.
- **Atomic per file when reasonable.** It makes `git log --oneline` and
  bisects far more useful.
- **Imperative mood** in the summary: "add", "fix", "remove" — not
  "added", "fixes", "removing".
- **No trailing period** on the summary.
- **No `Co-Authored-By` footers** unless the work was actually
  pair-authored.
- **Reference issues in the body**, not the title: `Closes #42`.

## Pull requests

Before pushing:

```bash
uv run ruff check --fix
uv run ruff format
uv run pytest
```

In your PR:

- Title follows Conventional Commits.
- One PR per logical change — bundling a refactor with a feature gets
  split on review.
- Add tests for new behavior, or explain why a test isn't applicable.
- Update the relevant doc page under `docs/` if user-visible behavior
  changes.

## Code of Conduct

By participating, you agree to abide by the
[Code of Conduct](CODE_OF_CONDUCT.md). Report incidents to
<goabonga@pm.me>.

## Security

Found a vulnerability? Don't open a public issue. See
[`.github/SECURITY.md`](.github/SECURITY.md) for the disclosure process.

## License

By contributing, you agree that your contributions will be licensed
under the project's [MIT license](LICENSE).
