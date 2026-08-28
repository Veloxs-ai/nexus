<!--
Thanks for contributing to Nexus!

A few things that help us review quickly:
  1. Read CONTRIBUTING.md if you haven't yet.
  2. Keep the PR focused — one concern per PR.
  3. Sign off your commits (`git commit -s`) for the DCO.
  4. If this touches security-sensitive code (security-governance, auth,
     the gateway, connectors, or subprocess wiring), say so below.
-->

## What & why

<!--
- *What* does this PR change?
- *Why* — what problem or use case motivated it?
- Link the issue it closes: `Closes #123`.
-->

## How I tested

<!--
- Which layer's test suite did you run?
- Did you add tests? List them.
- Any manual verification steps.
-->

## Layers touched

<!-- Tick all that apply. -->

- [ ] root (`src/nexus`)
- [ ] enterprise-data-pipeline
- [ ] data-processing-enrichment
- [ ] embedding-retrieval-intelligence
- [ ] orchestration-guardrails
- [ ] experience-api-engagement
- [ ] security-governance
- [ ] observability-monitoring
- [ ] docs
- [ ] CI / packaging

## Checklist

- [ ] I read [CONTRIBUTING.md](../CONTRIBUTING.md).
- [ ] My commits are signed off for the [DCO](../CONTRIBUTING.md#developer-certificate-of-origin) (`git commit -s`).
- [ ] The affected layer's `python -m pytest` is green locally.
- [ ] `ruff check .` and `ruff format --check .` pass.
- [ ] New `.py` files carry the Apache-2.0 SPDX header.
- [ ] Public-surface changes (new functions, CLI flags, config keys) are called out above.
- [ ] I updated the relevant docs (`README.md`, `docs/USING_NEXUS.md`, or a layer README).
- [ ] I added an entry to `CHANGELOG.md` under `[Unreleased]`.
- [ ] No new required runtime dependencies, or I justified each above.
- [ ] No layer imports another layer's Python code.
- [ ] No new cwd-relative library defaults.

## Security impact

<!--
Does this change touch authentication, authorization, cryptography,
tenancy, path resolution, subprocess invocation, or outbound network
calls? If yes, describe the impact. If no, write "None".
-->

## Breaking changes

<!--
If this is a breaking change, describe what breaks, who is affected, and
how integrators should migrate. Otherwise write "None".
-->
