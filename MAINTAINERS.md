# Maintainers

This file lists the people who can review, approve, and merge changes to
Nexus. Each maintainer is responsible for a slice of the project and is
the contact point for that area.

## Current maintainers

| Maintainer | GitHub | Area |
|---|---|---|
| (lead) | [@b-vermax](https://github.com/b-vermax) | All layers; security review; releases |

If you'd like to become a maintainer, sustained, high-quality
contributions in a specific layer are the path. Open a Discussion or
reach out to a current maintainer.

## How to reach maintainers

- **Public discussion**: [GitHub Discussions](https://github.com/Veloxs-ai/nexus/discussions)
- **Bugs / features**: [GitHub Issues](https://github.com/Veloxs-ai/nexus/issues)
- **Security**: see [SECURITY.md](SECURITY.md) — do **not** open a
  public issue
- **Code of Conduct enforcement**: conduct@veloxs.ai

## Review expectations

- Maintainers aim to acknowledge new PRs within **3 business days**
  (first comment or label, not necessarily a full review).
- Substantive review within **7 business days** for small PRs;
  larger PRs are negotiated.
- Security PRs are prioritized; see the response SLA in
  [SECURITY.md](SECURITY.md).

## Release process

Releases are cut by a maintainer with `release` permission. The process:

1. Ensure every layer's test suite is green on `main`.
2. Update `CHANGELOG.md`: move the `[Unreleased]` items into a new
   version section dated today.
3. Bump `version` in:
   - root `pyproject.toml`
   - each layer's `pyproject.toml`
   - each `src/<package>/__init__.py` `__version__`
4. Commit with `chore(release): vX.Y.Z` and open a PR.
5. After merge, tag the commit:
   ```bash
   git tag -s vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
6. Create a GitHub Release from the tag; paste the changelog entry as
   the release notes.
7. (Future) Publish the root and per-layer packages to PyPI.

## Security review

Any PR that touches code in `security-governance/`, the `auth.py` in
`experience-api-engagement/`, the connectors in
`enterprise-data-pipeline/`, or the subprocess wiring in `src/nexus/`
requires a maintainer with security review responsibility to approve.
Mark such PRs with the `security-review` label.
