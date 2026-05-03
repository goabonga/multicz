# Security policy

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Use one of these private channels:

- **Preferred:** GitHub's private vulnerability reporting —
  <https://github.com/goabonga/multicz/security/advisories/new>
- Email: <goabonga@pm.me>

Include:

- A description of the vulnerability and its impact
- Steps to reproduce or a proof-of-concept
- The affected version (`multicz --version`)

You should receive an acknowledgment within 72 hours. The aim is a fix
within 14 days for high-severity issues, coordinated with you before any
public disclosure.

## Supported versions

Only the latest minor release on PyPI receives security fixes. multicz
follows semver, so upgrading within the same minor is non-breaking.

## Threat model

multicz is a release tool: it modifies version files, writes commits,
creates tags, and (with `--push`) sends them to remote. It has no network
access by default, no auto-updates, no implicit remote state. For the
full set of guarantees and CI hardening recommendations, see the
[Security page in the docs](https://goabonga.github.io/multicz/security/).
