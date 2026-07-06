# Developing Nexus

Nexus is proprietary and confidential software, © 2026 Veloxs AI Inc., all
rights reserved. This guide is for the Veloxs AI Inc. engineering team and
authorized collaborators working on Nexus internally. It is **not** an
invitation for external/public contributions; access to this repository is
governed by the Nexus Proprietary Software License and any applicable
agreement with Veloxs AI Inc.

For security-sensitive reports, follow the process in [SECURITY.md](SECURITY.md).
Code ownership and the release process live in [MAINTAINERS.md](MAINTAINERS.md).

---

## Project conventions you must keep

These are load-bearing — read before opening an internal change.

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
5. **Security-affecting changes need explicit review.** Open a draft change
   early and request review from a code owner (see [MAINTAINERS.md](MAINTAINERS.md)).
6. **Don't widen the public surface without discussion.** If you're adding
   a new public function, class, CLI command, or config key, call it out so
   it can be considered intentionally.
7. **Every source file carries the proprietary copyright header.** New
   `.py` files must start with the standard `Copyright 2026 Veloxs AI Inc.`
   / `SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary` header.

---

## Development workflow

### 1. Clone (internal repository)

```bash
git clone <internal-repo-url> nexus
cd nexus
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

Keep commits scoped and reviewable.

### 8. Open an internal review

- Describe the *what* and the *why*.
- Link the tracking item it closes.
- Note any breaking changes prominently.
- Update `CHANGELOG.md` under the `## [Unreleased]` heading.
- Ensure CI is green.

---

## What gets reviewed faster

- **Small, focused changes** — one concern at a time.
- **Tests for new behavior** — if it's not tested, it can regress.
- **Updated docs** — if you change a CLI flag, config key, or public
  function, update the corresponding `README.md` and `docs/USING_NEXUS.md`.
- **CHANGELOG entries** — one line under `[Unreleased]` in the right
  category (`Added`, `Changed`, `Fixed`, `Security`, `Deprecated`,
  `Removed`).
- **Self-review** — read your own diff before requesting review.

## What slows things down

- Mixing refactor + feature + bug fix in one change.
- Public-surface changes without rationale.
- New runtime dependencies without justification (we prefer the standard
  library + the dependencies already in `pyproject.toml`).
- Adding cwd-relative defaults — these break library users (see the
  *Library defaults* limitation in [SECURITY.md](SECURITY.md)).
- Skipping tests for "obvious" changes.

---

## Adding a new dependency

We try to stay light. Before adding a runtime dependency:

1. Explain the use case in the change description.
2. Check whether the standard library or an already-present dep can do
   the job.
3. Confirm the dependency's license is permissive and **non-copyleft** so
   it can ship inside proprietary software (MIT, BSD-2/3, Apache-2.0, ISC,
   PSF are fine; GPL / AGPL / other copyleft licenses are not). Do not add
   third-party code with incompatible or unclear licensing.
4. Pin it with a sensible floor (e.g. `cryptography>=42.0.0`) but avoid
   capping the upper bound unless there's a known breaking change.
5. Update `NOTICE` with the dependency's name and license.

---

## Questions

If anything here is unclear, raise it with a code owner (see
[MAINTAINERS.md](MAINTAINERS.md)) before doing work that has to be reshaped
on review.
