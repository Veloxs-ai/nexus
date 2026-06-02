<!--
Thanks for contributing to Nexus. A few things that help us merge faster:

1. Read CONTRIBUTING.md if you haven't.
2. Keep the PR focused — one concern per PR.
3. If this touches security-sensitive code (security-governance,
   experience auth, connectors, subprocess wiring), add the
   `security-review` label.
-->

## What & why

<!--
- *What* does this PR change?
- *Why* — what use case or bug motivated it?
- Link the issue it closes: `Closes #123`.
-->

## How I tested

<!--
- Which layer's pytest suite did you run?
- Did you add new tests? List them.
- Manual verification steps if any.
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
- [ ] The affected layer's `python -m pytest` is green locally.
- [ ] I ran `ruff check` and `ruff format` on the affected files.
- [ ] Public-surface changes (new functions, CLI flags, config keys) are
      called out in the description above.
- [ ] I updated relevant docs (`README.md`, `docs/USING_NEXUS.md`, or
      layer READMEs).
- [ ] I added an entry to `CHANGELOG.md` under `[Unreleased]`.
- [ ] Commits are signed off (`git commit -s`).
- [ ] No new runtime dependencies, or I justified each in the description.
- [ ] No layer imports another layer's Python code.
- [ ] No new cwd-relative library defaults.

## Breaking changes

<!--
If this PR is a breaking change, describe what breaks, who is affected,
and how integrators should migrate. Otherwise write "None".
-->

## Screenshots / output (optional)

<!-- Only if relevant — e.g. for docs PRs, CLI changes, or REST API responses. -->
