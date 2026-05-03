---
icon: lucide/shield
---

# Security

Multicz is a release tool: it modifies version files, writes commits,
creates tags, and (with `--push`) sends them to a remote. The threat
model is straightforward — the security guarantees should match.

## Properties guaranteed by the implementation

- **No network access by default.** Multicz only invokes `git`. There
  are no HTTP calls, no fetching of registries, no auto-updates. The
  network only enters the picture when *you* pass `--push`.
- **Deterministic planning.** Same git history + same `multicz.toml`
  yields the same plan. There's no implicit time-of-day, no remote
  state lookup, no learned heuristic. Repeat runs are byte-identical
  (modulo the timestamp written into `CHANGELOG.md`,
  `debian/changelog`, and `state.json`, which is wall-clock UTC).
- **Explicit changed files from git.** Multicz uses
  `git diff-tree --name-only` per commit — the exact set of paths
  actually touched, not heuristics. A `path_overlap` finding from
  `validate` reads from `git ls-files`; nothing is sniffed from a
  watcher or filesystem scan.
- **No code execution from config.** The TOML schema is
  pydantic-validated with `extra="forbid"`. There are no callbacks,
  no Python imports from data, no shell-out templates.

The single exception is `post_bump`: each entry is a shell command
parsed via `shlex.split` and executed in the repo root. Treat
`post_bump` like any other CI shell hook — review what's there, and
keep `multicz.toml` itself under the same code-review process as the
rest of the repo.

## Hardening options

| concern | option |
|---|---|
| Tampered release commits | `[project].sign_commits = true` ([details][sign_commits]) or `multicz bump --sign` (passes `-S` to `git commit`) |
| Tampered tags | `[project].sign_tags = true` ([details][sign_tags]) or `multicz bump --sign` (passes `-s` to `git tag`) |
| Manual edits bypassing the bump flow | `[project].state_file` ([details][state_file]) + `multicz validate` (drift detection) |
| Non-conventional commits sneaking into a release | `[project].unknown_commit_policy = "error"` ([details][unknown_commit_policy]) |
| Overlapping component paths leaking changes silently | `[project].overlap_policy = "error"` ([details][overlap_policy]) (default) |

[sign_commits]: configuration.md#sign_commits
[sign_tags]: configuration.md#sign_tags
[state_file]: configuration.md#state_file
[unknown_commit_policy]: configuration.md#unknown_commit_policy
[overlap_policy]: configuration.md#overlap_policy
| Path / mirror / trigger cycles | [`multicz validate`](cli.md#validate) — runs as a CI gate before `bump` |

## CI hardening checklist

1. **Pin `multicz`** by exact version in your CI install step
   (`pip install multicz==1.2.0` or
   `uv tool install --frozen multicz`).
2. **Run `multicz validate --strict` first.** It catches misconfigured
   `bump_files`, mirror cycles, and path overlaps before anything is
   written.
3. **Use `multicz plan --dry-run`** (or `multicz plan --output json`)
   to inspect the bump in PR previews, not at release time.
4. **Sign commits and tags** in CI. GitHub Actions accepts a GPG key
   via `crazy-max/ghaction-import-gpg`; GitLab via
   `git config user.signingkey` then enabling `sign_commits` /
   `sign_tags` in `multicz.toml`.
5. **Limit who can `--push`.** Multicz never pushes unless asked.
   Keep the release job behind a manual approval / protected branch.
6. **Audit the state file** if you've enabled it.
   `git log -p .multicz/state.json` gives a tamper-evident trail of
   every release.

The example pipelines in
[`examples/ci/`](https://github.com/goabonga/multicz/tree/main/examples/ci)
follow these recommendations.

## Drift detection

When `[project].state_file` is set, `multicz validate` adds two checks:

- **`state_drift`** (warning) — the recorded version doesn't match the
  current value in the primary `bump_file`. Fires when someone edits
  `pyproject.toml`, `Chart.yaml`, or `package.json` manually without
  going through `multicz bump`:

  ```
  ! api: state recorded version '1.3.0' but pyproject.toml now reads
    '9.9.9' — someone may have edited the file outside multicz bump
    (state_drift)
  ```

- **`state_unknown_component`** (warning) — the state references a
  name no longer declared in `multicz.toml` (typically after a
  component was renamed or removed without clearing state).

Treat them as errors in CI by adding `--strict`:

```bash
multicz validate --strict
```

The state file is **opt-in**. The default stateless flow remains the
recommended setup for most repos — the planner always re-derives from
git, which is the source of truth.

## Exit codes

| command | code | meaning |
|---|---|---|
| `validate` | 0 | clean (warnings/info don't fail) |
| `validate` | 1 | at least one error |
| `validate --strict` | 2 | at least one warning |
| `bump` (no commits, no `--force`) | 0 | "nothing to do" — success |
| `plan` (with `unknown_commit_policy = "error"` and offenders) | 1 | refuses to plan, lists every offending SHA |

Use these for explicit gating — e.g. fail the pipeline on `validate`
warnings without merging the workflow logic with `bump` itself.
