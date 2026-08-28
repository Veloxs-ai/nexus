# Maintainers and governance

Nexus — the Enterprise Intelligence Framework — is an open-source project stewarded by **Veloxs AI Inc.**, which holds the copyright and makes final decisions on project direction, releases, and the public API.

This file records who maintains what, how decisions get made, and how releases are cut. If you are looking for how to *contribute*, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Governance model

Nexus uses a **benevolent-maintainer** model. Veloxs AI Inc. maintains the project, reviews and merges contributions, and decides what ships. There is no formal steering committee or voting process.

This means, concretely:

- Anyone may open issues, discussions, and pull requests.
- Maintainers review contributions on their merits and against the [project conventions](CONTRIBUTING.md#project-conventions).
- Veloxs AI Inc. has the final say on scope, API design, and release timing.
- Contributions are accepted under Apache-2.0 with a [DCO sign-off](CONTRIBUTING.md#developer-certificate-of-origin). Contributors retain copyright in their own contributions.

If the project grows enough to warrant broader governance, that change will be proposed publicly here before it takes effect.

---

## Maintainers

| Area | Maintainer | Contact |
|---|---|---|
| All layers, security review, releases | Veloxs AI Inc. engineering | engineering@veloxs.ai |

Maintainer responsibilities are assigned internally by Veloxs AI Inc. We would like to add maintainers from the community as the project grows — sustained, high-quality contribution is the path.

### Areas requiring security review

A maintainer with security-review responsibility must approve any change touching:

- `security-governance/` — RBAC, tenancy, encryption, audit
- `experience-api-engagement/src/nexus_experience/auth.py` — authentication
- `experience-api-engagement/src/nexus_experience/gateway.py` — path resolution
- `enterprise-data-pipeline/src/nexus_pipeline/connectors/` — outbound network
- `src/nexus/platform.py` — subprocess wiring

---

## Contact

- **General questions** → [Discussions](https://github.com/Veloxs-ai/nexus/discussions) or [SUPPORT.md](SUPPORT.md)
- **Security vulnerabilities** → [SECURITY.md](SECURITY.md) — **never** a public issue
- **Code of Conduct concerns** → conduct@veloxs.ai
- **Trademark, licensing, or legal** → legal@veloxs.ai
- **Commercial inquiries** → hello@veloxs.ai

---

## Response expectations

Nexus is maintained on a best-effort basis alongside commercial work. These are targets, not guarantees — the open-source project carries no support SLA. See [SUPPORT.md](SUPPORT.md).

| | Target |
|---|---|
| Issue triage | Best effort, usually within a week |
| Pull request acknowledgment | Best effort, usually within a week |
| Security reports | Prioritized — see the SLA in [SECURITY.md](SECURITY.md) |

---

## Release process

Nexus follows [Semantic Versioning](https://semver.org/). Breaking changes to the public API ship only in major releases.

Releases are cut by a maintainer with release permission:

1. Confirm every layer's test suite is green on `main`, along with lint, license-header, and build checks.
2. Update `CHANGELOG.md`: move `[Unreleased]` items into a new dated version section.
3. Bump `version` in the root `pyproject.toml`, each layer's `pyproject.toml`, and `__version__` in `src/nexus/__init__.py`. Keep them in step.
4. Update `configs/nexus.json` → `platform.version`.
5. Commit as `chore(release): vX.Y.Z` and open a PR.
6. After merge, tag the commit:
   ```bash
   git tag -s vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
7. The `publish` workflow builds and publishes to PyPI via Trusted Publishing (OIDC) — no long-lived API token is stored in the repository.
8. Draft the GitHub release from the changelog section, attaching the built artifacts.

### Distribution channels

Nexus is published to:

- **PyPI** — [`veloxs-nexus`](https://pypi.org/project/veloxs-nexus/)
- **GitHub Releases** — tagged source and built distributions

Build artifacts are **never** committed to the repository; `build/` and `dist/` are gitignored.

---

## Trademark policy

The Nexus and Veloxs AI names, logos, and branding are trademarks of Veloxs AI Inc. and are **not** licensed under Apache-2.0 (see Section 6 of the license, and [NOTICE](NOTICE)).

Maintainers will ask contributors to rename forks or derivative distributions that use these marks in a way implying endorsement or official status. Truthful statements of compatibility ("built on Nexus") are always fine.
