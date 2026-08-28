# Getting help with Nexus

Nexus — the Enterprise Intelligence Framework — is an open-source project maintained by Veloxs AI Inc. This page explains where to ask what, and what response you can reasonably expect.

**Please do not use the issue tracker for usage questions** — it is for defects and feature proposals. Questions get better answers in Discussions, and keeping them separate helps maintainers triage real bugs.

---

## Start with the documentation

Most questions are answered here:

| I want to… | Read |
|---|---|
| Install Nexus and run something | [README — Quick start](README.md#quick-start) |
| Understand how the pieces fit | [README — Architecture](README.md#architecture) · [docs/architecture.md](docs/architecture.md) |
| Integrate Nexus into an application | [docs/USING_NEXUS.md](docs/USING_NEXUS.md) |
| Configure a layer | [README — Configuration](README.md#configuration) |
| Understand chunking and embeddings | [docs/PROCESSING_AND_EMBEDDING_SPEC.md](docs/PROCESSING_AND_EMBEDDING_SPEC.md) |
| Understand the security model | [SECURITY.md](SECURITY.md) |
| Contribute a change | [CONTRIBUTING.md](CONTRIBUTING.md) |
| See what changed between versions | [CHANGELOG.md](CHANGELOG.md) |

---

## Where to ask

### 💬 Questions, ideas, and help — [GitHub Discussions](https://github.com/Veloxs-ai/nexus/discussions)

The right place for:

- "How do I do X with Nexus?"
- "Is this the intended way to use Y?"
- "Has anyone integrated Nexus with Z?"
- Showing off what you built
- Proposing an idea before it becomes a formal feature request

### 🐛 Bugs — [Issue tracker](https://github.com/Veloxs-ai/nexus/issues)

Open a [bug report](https://github.com/Veloxs-ai/nexus/issues/new?template=bug_report.yml) when something behaves differently than documented. Please include:

- Nexus version (`pip show veloxs-nexus`) and Python version
- Which layer is involved
- A **minimal reproduction** — the smallest snippet that shows the problem
- What you expected, and what actually happened
- The full traceback, if there is one

A reproduction is the single most useful thing you can provide. Bugs without one usually stall.

### ✨ Feature requests — [Issue tracker](https://github.com/Veloxs-ai/nexus/issues/new?template=feature_request.yml)

Describe the **problem you are trying to solve** before the solution you have in mind. Use cases shape better APIs than proposed signatures do.

### 🔐 Security vulnerabilities — **not** in public

Follow the private disclosure process in [SECURITY.md](SECURITY.md). Do not open a public issue, discussion, or pull request for a vulnerability.

### 🤝 Code of Conduct concerns — **conduct@veloxs.ai**

Reported privately and handled per [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

## What to expect

Nexus is maintained on a best-effort basis by Veloxs AI Inc. alongside commercial work. There is no support SLA for the open-source project.

| | Typical target |
|---|---|
| Discussion replies | Best effort, usually within a week |
| Bug triage | Best effort, usually within a week |
| Pull request acknowledgment | Best effort, usually within a week |
| Security reports | See the SLA in [SECURITY.md](SECURITY.md) |

Security reports are prioritized above everything else. If a thread goes quiet, a polite follow-up is welcome and not considered rude.

---

## Supported versions

Only the latest release line receives fixes. See [SECURITY.md](SECURITY.md#supported-versions) for the security-support policy specifically.

Nexus follows [Semantic Versioning](https://semver.org/). Breaking changes to the public API arrive only in major releases and are called out in [CHANGELOG.md](CHANGELOG.md).

---

## Commercial support

Veloxs AI Inc. offers commercial support for Nexus — guaranteed response times, deployment assistance, and managed hosting — for organizations that need it. Contact **hello@veloxs.ai**.

Commercial support is entirely optional. Nexus is fully functional, permissively licensed, and complete on its own. No feature is deliberately withheld from the open-source project.
