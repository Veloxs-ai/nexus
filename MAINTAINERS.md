# Code Owners

Nexus is proprietary software owned by Veloxs AI Inc. This file lists the
people responsible for reviewing, approving, and releasing changes. Each
owner is the contact point for their area.

## Current code owners

| Owner | Contact | Area |
|---|---|---|
| (lead) | engineering@veloxs.ai | All layers; security review; releases |

Code-owner responsibilities are assigned internally by Veloxs AI Inc.

## How to reach the team (internal / authorized collaborators)

- **Engineering**: engineering@veloxs.ai
- **Security**: see [SECURITY.md](SECURITY.md)
- **Conduct concerns**: conduct@veloxs.ai
- **Licensing / pilot inquiries**: legal@veloxs.ai

## Review expectations

- Owners acknowledge new internal changes within **3 business days**.
- Substantive review within **7 business days** for small changes; larger
  changes are negotiated.
- Security changes are prioritized; see the response SLA in
  [SECURITY.md](SECURITY.md).

## Release process

Releases are cut by a code owner with release permission:

1. Ensure every layer's test suite is green on the release branch.
2. Update `CHANGELOG.md`: move the `[Unreleased]` items into a new
   version section dated today.
3. Bump `version` in:
   - root `pyproject.toml`
   - each layer's `pyproject.toml`
   - each `src/<package>/__init__.py` `__version__`
4. Commit with `chore(release): vX.Y.Z` and open an internal review.
5. After merge, tag the commit:
   ```bash
   git tag -s vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
6. Distribute the build through the approved internal/customer channel per
   the applicable agreement. Nexus is not published to public package
   indexes.

## Security review

Any change that touches code in `security-governance/`, the `auth.py` in
`experience-api-engagement/`, the connectors in
`enterprise-data-pipeline/`, or the subprocess wiring in `src/nexus/`
requires a code owner with security-review responsibility to approve.
