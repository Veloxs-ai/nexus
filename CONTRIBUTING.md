# Contributing to Nexus

Thanks for your interest in improving Nexus. This guide explains how to
set up a development environment, what we look for in contributions, and
how to land a change.

By participating in this project you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md). For security-sensitive reports,
follow the process in [SECURITY.md](SECURITY.md) instead of opening a
public issue.

---

## How to contribute

| You want to… | Start here |
|---|---|
| File a bug | Open an issue using the **Bug report** template |
| Request a feature | Open an issue using the **Feature request** template — describe the use case, not just the API |
| Report a vulnerability | **Do not open an issue.** Follow [SECURITY.md](SECURITY.md) |
| Ask a question | Use [Discussions](https://github.com/Veloxs-ai/nexus/discussions) (preferred) rather than opening an issue |
| Submit code | Fork → branch → PR. See "Development workflow" below |
| Improve docs | PRs welcome; docs live in `docs/` and per-layer `README.md` files |

---

## Project conventions you must keep

These are load-bearing — please read before sending a PR.

1. **No layer may import another layer's Python code.** Layers integrate
   through configs, JSONL contracts, CLI / subprocess, or HTTP. This is
   what makes each layer independently deployable.
2. **No side effects at import time.** Package `__init__.py` files should
   re-export only. No logging configuration, no `sys.path` mutation, no
   `os.environ` writes.
3. **No `eval`, `exec`, `pickle`, `os.system`, `shell=True`.** YAML is
   loaded with `yaml.safe_load`. HTTP uses `httpx` with TLS verification
   enabled.
4. **Tests stay deterministic and offline.** No network calls, no real
   cloud services. Mock or use file-backed local implementations.
5. **Security-affecting changes need explicit review.** Open a draft PR
   early and CC a maintainer (see [MAINTAINERS.md](MAINTAINERS.md)).
6. **Don't widen the public surface without discussion.** If you're adding
   a new public function, class, CLI command, or config key, mention it
   in the PR description so we can consider it intentionally.

---

## Development workflow

### 1. Fork and clone

```bash
git clone https://github.com/<your-username>/nexus.git
cd nexus
git remote add upstream https://github.com/Veloxs-ai/nexus.git
```

### 2. Create a Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 3. Install the layer(s) you're touching

Each layer is its own installable project. Install just the ones you'll
work on:

```bash
cd <layer-folder>
python -m pip install -e ".[dev]"
```

Some layers have extras — e.g. `experience-api-engagement` has `[api]`
for FastAPI + uvicorn.

### 4. Create a branch

```bash
git checkout -b feat/<short-description>      # for features
git checkout -b fix/<short-description>       # for bug fixes
git checkout -b docs/<short-description>      # for docs-only changes
git checkout -b chore/<short-description>     # for build/CI/dependency bumps
```

### 5. Make the change + test

```bash
# Run the affected layer's suite
cd <layer-folder>
python -m pytest -q

# Or run everything (from repo root)
python -m pytest
for layer in enterprise-data-pipeline data-processing-enrichment embedding-retrieval-intelligence orchestration-guardrails experience-api-engagement security-governance observability-monitoring; do
  (cd "$layer" && python -m pytest -q) || break
done
```

All suites should be green before you push.

### 6. Lint and format

We use [Ruff](https://docs.astral.sh/ruff/) for both lint and format,
configured per-layer in `pyproject.toml`:

```bash
ruff check .
ruff format .
```

### 7. Commit

We use [Conventional Commits](https://www.conventionalcommits.org/)
loosely. Examples:

```
feat(security): add KMS-backed key material adapter
fix(pipeline): refuse cross-origin next links in RestApiConnector
docs: clarify auth.max_query_chars default
test(guardrails): add zero-width obfuscation case for prompt security
chore(deps): bump cryptography to 44.0
```

Keep commits scoped and reviewable. Squashing on merge is fine for small
PRs; for larger PRs we prefer clean per-commit history.

### 8. Open a pull request

- Use the PR template — it asks for the *what* and the *why*.
- Link the issue it closes (`Closes #123`).
- Note any breaking changes prominently in the description.
- Update `CHANGELOG.md` under the `## [Unreleased]` heading.
- Ensure CI is green.

---

## What gets merged faster

- **Small, focused PRs** — one concern per PR.
- **Tests for new behavior** — if it's not tested, it can regress.
- **Updated docs** — if you change a CLI flag, config key, or public
  function, update the corresponding `README.md` and `docs/USING_NEXUS.md`.
- **CHANGELOG entries** — one line under `[Unreleased]` in the right
  category (`Added`, `Changed`, `Fixed`, `Security`, `Deprecated`,
  `Removed`).
- **Self-review** — read your own diff in the GitHub UI before requesting
  review; you'll catch half of what a reviewer would flag.

## What slows things down

- Mixing refactor + feature + bug fix in one PR.
- Public-surface changes without rationale.
- New runtime dependencies without justification (we prefer the standard
  library + the dependencies already in `pyproject.toml`).
- Adding cwd-relative defaults — these break library users (see the
  *Library defaults* limitation in [SECURITY.md](SECURITY.md)).
- Skipping tests for "obvious" changes.

---

## Adding a new dependency

We try to stay light. Before adding a runtime dependency:

1. Open an issue or PR description explaining the use case.
2. Check whether the standard library or an already-present dep can do
   the job.
3. Confirm the dependency's license is compatible with Apache-2.0 (MIT,
   BSD-2/3, Apache-2.0, ISC, PSF are all fine; GPL / AGPL / proprietary
   are not).
4. Pin it with a sensible floor (e.g. `cryptography>=42.0.0`) but avoid
   capping the upper bound unless there's a known breaking change.
5. Update `NOTICE` with the dependency's name and license.

---

## Releasing (maintainers)

See [MAINTAINERS.md](MAINTAINERS.md) for the release checklist. Public
contributors do not need to bump versions.

---

## DCO / sign-off

We require contributors to sign off their commits using the
[Developer Certificate of Origin](https://developercertificate.org/):

```bash
git commit -s -m "feat(security): add KMS adapter"
```

This adds a `Signed-off-by: Your Name <you@example.com>` trailer that
asserts you have the right to contribute the change under the project's
license.

---

## Questions

If anything in this document is unclear, open a thread in
[Discussions](https://github.com/Veloxs-ai/nexus/discussions). Better to
ask early than to do work that has to be reshaped on review.

Thanks again for contributing.
