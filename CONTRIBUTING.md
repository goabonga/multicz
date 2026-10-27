# Contributing to multicz

Thanks for taking the time to contribute. This guide covers the setup,
development loop, and the conventions multicz uses for branches and
commits - both of which drive the project's own release pipeline.

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
ruff, mypy, pyright, pre-commit) into `.venv/`. Add `--group docs` to also
install Zensical for the documentation site.

Install the pre-commit and commit-msg hooks once per clone. They run ruff
check and format, mypy, pyright, the SPDX header checks and the
Conventional Commits validation before each commit lands:

```bash
uv run pre-commit install
uv run pre-commit run --all-files   # run every hook on the whole tree
```

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

### Type checks

Two checkers run on `src/`, because mypy and pyright disagree on inference
and narrowing and each catches what the other lets through:

```bash
uv run mypy src                  # config: [tool.mypy]
uv run pyright                   # config: [tool.pyright]
```

CI runs both next to the tests, the SPDX header check and the security
scans (bandit, pip-audit, osv-scanner), and all of them gate the release.
Each job writes a summary of its result on the run page.

### License headers

Every Python and workflow file starts with the two-line SPDX header (after
the shebang, if any):

```
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Chris <goabonga@pm.me>
```

```bash
python3 scripts/add_license_header.py --path src --types py          # add
python3 scripts/add_license_header.py --path .github --types yml --check
```

### Documentation site (optional)

```bash
uv sync --group docs
uv run zensical serve            # http://localhost:8000
uv run zensical build --strict   # validate links + render
```

The doc site is the user-facing source of truth - when you change
behavior, update the relevant page under `docs/`.

## Branches and merging

### Branch names

A branch is named after the GitHub issue it addresses:

```
issue-<number>-<slug>
```

`<number>` is the issue number and `<slug>` a few lowercase words separated
by hyphens, for example `issue-12-writers-regex-prefix`. Keep it free of
`/`: Git cannot hold `issue-12` and `issue-12/...` at the same time, and
the automation only recognises `issue-*` as a base branch.

| Work | Branch | Created from | Pull request into |
| --- | --- | --- | --- |
| An issue | `issue-<number>-<slug>` | `main` | `main` |
| A sub-issue of an issue | `issue-<number>-<slug>` (its own issue number) | the branch of the parent issue | the branch of the parent issue |

An issue split into sub-issues therefore gets one branch of its own, which
collects the pull requests of its sub-issues. Once they are all merged, the
issue branch is proposed to `main` in a single pull request. Dependabot
branches (`dependabot/...`) are created by Dependabot and need no naming.

The conventional commit type is carried by the commits and the pull request
title, not by the branch name.

### Signed commits and merging

`main` and the `issue-*` branches require signed commits, a linear history,
a pull request and the CI checks. A pull request is merged by adding the
`auto-merge` label, which needs write access: the workflow replays its
commits GPG-signed onto the base branch once the required checks passed,
then fast-forwards that branch, `main` or the issue branch of a sub-issue.
The commits of a branch pushed unsigned, such as by GitHub's "Update
branch", are re-signed in place.

Dependabot pull requests are rewritten as Conventional Commits and signed.
Minor and patch updates are queued for the same merge once CI passed; a
major update only gets a notice and waits for a maintainer to add the
label.

Each Dependabot pull request also gets an issue, assigned to the repository
owner, which the pull request closes when it is merged. If the pull request
is closed without a merge, the issue is closed as not planned.

The automation needs the `AUTO_MERGE_PAT`, `GPG_PRIVATE_KEY` and
`GPG_PASSPHRASE` secrets and the `GIT_USER_NAME`, `GIT_USER_EMAIL` and
`GIT_SIGNING_KEY` variables of the repository. The release job pushes its
commit and tags with the same token, because the `main` ruleset does not
let the workflow token do it.

## Commit messages

multicz uses [Conventional Commits](https://www.conventionalcommits.org/)
because its own release pipeline reads them:

```
<type>(<optional-scope>): <imperative summary>

<optional body explaining the why>

<optional footer - BREAKING CHANGE: ..., refs, etc.>
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
- **Imperative mood** in the summary: "add", "fix", "remove" - not
  "added", "fixes", "removing".
- **No trailing period** on the summary, at most 72 characters, and a
  lowercase first word after the colon. The signed merge refuses any other
  subject, so the `commit-subject` pre-commit hook and the `commit-subjects`
  CI job check it first.
- **No `Co-Authored-By` footers** unless the work was actually
  pair-authored.
- **Reference issues in the body**, not the title: `Closes #42`.

## Pull requests

Before pushing, run the hooks (they mirror the CI checks) and the tests:

```bash
uv run pre-commit run --all-files
uv run pytest
```

In your PR:

- Open it against `main`, or against the issue branch for a sub-issue.
- Title follows Conventional Commits.
- One PR per logical change - bundling a refactor with a feature gets
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
