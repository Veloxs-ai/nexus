# Contributing to Nexus

Thanks for your interest in **Nexus — the Enterprise Intelligence Framework**. Contributions of all kinds are welcome — bug reports, documentation fixes, new connectors, performance work, and larger features.

This guide covers how to get set up, the conventions the project holds to, and what happens to your pull request.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Contents

- [Ways to contribute](#ways-to-contribute)
- [Developer Certificate of Origin](#developer-certificate-of-origin)
- [Development setup](#development-setup)
- [Project conventions](#project-conventions)
- [Making a change](#making-a-change)
- [Opening a pull request](#opening-a-pull-request)
- [Adding a dependency](#adding-a-dependency)
- [Questions](#questions)

---

## Ways to contribute

- **Report a bug** — [open a bug report](https://github.com/Veloxs-ai/nexus/issues/new?template=bug_report.yml) with a minimal reproduction.
- **Request a feature** — [open a feature request](https://github.com/Veloxs-ai/nexus/issues/new?template=feature_request.yml) describing the use case, not just the proposed API.
- **Report a vulnerability** — **do not open a public issue.** Follow [SECURITY.md](SECURITY.md).
- **Improve documentation** — often the highest-value contribution. Typo fixes need no prior discussion.
- **Write code** — for anything beyond a small fix, open an issue first so the approach can be agreed before you invest time.

Issues labelled [`good first issue`](https://github.com/Veloxs-ai/nexus/labels/good%20first%20issue) are scoped for newcomers.

---

## Developer Certificate of Origin

Nexus uses the [Developer Certificate of Origin](https://developercertificate.org/) (DCO). It is a lightweight assertion that you wrote the contribution or otherwise have the right to submit it under Apache-2.0. There is no CLA to sign.

Sign off each commit by adding a `Signed-off-by` line, which `git` adds for you with `-s`:

```bash
git commit -s -m "fix(pipeline): reject cross-origin next links"
```

This appends:

```
Signed-off-by: Your Name <your.email@example.com>
```

Use your real name and an address you can be reached at. To sign off commits you already made:

```bash
git rebase --signoff main
```

Your contribution is licensed under Apache-2.0, the same license as the project. Copyright in your contribution remains yours; Section 5 of the license grants the project the rights it needs.

---

## Development setup

Nexus requires **Python 3.11 or 3.12**.

### 1. Fork and clone

```bash
git clone https://github.com/<your-username>/nexus.git
cd nexus
git remote add upstream https://github.com/Veloxs-ai/nexus.git
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
```

### 3. Install the root package

```bash
python -m pip install -e ".[dev]"
```

This installs Nexus in editable mode with `pytest` and `ruff`.

### 4. Install the layers you are touching

Each of the seven layers is its own installable project with its own test suite:

```bash
cd embedding-retrieval-intelligence
python -m pip install -e ".[dev]"
```

`experience-api-engagement` has an extra `[api]` for FastAPI and uvicorn.

### 5. Confirm everything passes

```bash
python -m pytest -q          # root suite
ruff check .
ruff format --check .
```

If this is not green on a fresh clone, that is a bug — please report it.

---

## Project conventions

These are load-bearing. A change that breaks one of them will be asked to change.

1. **No layer imports another layer's Python code.** Layers integrate through configs, JSONL contracts, CLI/subprocess, and HTTP. This is what makes each layer independently deployable and replaceable.

2. **No side effects at import time.** Package `__init__.py` files re-export only — no logging configuration, no `sys.path` mutation, no `os.environ` writes, no file or network I/O.

3. **No `eval`, `exec`, `pickle`, `os.system`, or `shell=True`.** YAML is loaded with `yaml.safe_load`. HTTP goes through the hardened `urllib` wrapper in `nexus.pipeline.connectors`, which refuses redirects and cross-origin `next` links.

4. **No implicit secret lookups in library code.** Never read a secret from the environment as a silent fallback inside a library function. Take it as an explicit parameter, or use the documented `env:VAR_NAME` indirection at the config boundary.

5. **Tests stay deterministic and offline.** No network calls, no real cloud services, no model downloads, no wall-clock or random dependence without a seed. Mock or use file-backed local implementations.

6. **No cwd-relative defaults in library code.** These break library consumers whose working directory you do not control. Take a `base_dir` explicitly.

7. **Every `.py` file carries the Apache-2.0 header.** New files start with:

   ```python
   # Copyright 2026 Veloxs AI Inc.
   #
   # Licensed under the Apache License, Version 2.0 (the "License");
   # you may not use this file except in compliance with the License.
   # You may obtain a copy of the License at
   #
   #     http://www.apache.org/licenses/LICENSE-2.0
   #
   # Unless required by applicable law or agreed to in writing, software
   # distributed under the License is distributed on an "AS IS" BASIS,
   # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   # See the License for the specific language governing permissions and
   # limitations under the License.
   #
   # SPDX-License-Identifier: Apache-2.0
   ```

   CI enforces this. Keep the existing copyright line; do not add your own copyright notice to existing files.

8. **Don't widen the public surface casually.** New public functions, classes, CLI commands, or config keys should be called out in the PR description so they can be considered deliberately. Public API is a promise.

---

## Making a change

### Branch

```bash
git checkout -b feat/short-description     # features
git checkout -b fix/short-description      # bug fixes
git checkout -b docs/short-description     # docs only
git checkout -b chore/short-description    # build, CI, dependencies
```

### Test

Run the suite for every layer you touched, plus the root:

```bash
cd <layer-folder> && python -m pytest -q
```

New behavior needs a test. A bug fix should come with a test that fails before the fix and passes after.

### Lint and format

```bash
ruff check . --fix
ruff format .
```

The ruff configuration is pinned in `pyproject.toml` with an explicit rule selection, so results are reproducible across versions.

### Commit

We follow [Conventional Commits](https://www.conventionalcommits.org/) loosely:

```
feat(security): add KMS-backed key material adapter
fix(pipeline): refuse cross-origin next links in RestApiConnector
docs: clarify auth.max_query_chars default
test(guardrails): add zero-width obfuscation case
chore(deps): bump cryptography to 44.0
```

Keep commits scoped and reviewable. Remember `-s` for the DCO sign-off.

---

## Opening a pull request

1. Push your branch and open a PR against `main`.
2. Fill in the [pull request template](.github/pull_request_template.md) — what changed, why, and how you tested it.
3. Add an entry to `CHANGELOG.md` under `## [Unreleased]` in the right category.
4. Make sure CI is green: tests, ruff, license headers, and the build all run automatically.

### What gets reviewed quickly

- Small, focused changes — one concern per PR.
- Tests that demonstrate the new behavior or the fixed bug.
- Updated docs when a CLI flag, config key, or public function changes.
- A self-review: read your own diff before requesting review.

### What slows things down

- Mixing a refactor, a feature, and a bug fix in one PR.
- Public-surface changes without a rationale.
- New runtime dependencies without justification.
- Skipping tests because the change looks obvious.

### What to expect

Maintainers aim to acknowledge new PRs within about a week. This is a best-effort open-source project, not a support contract — if a PR goes quiet, a polite ping on the thread is welcome.

Security-sensitive changes — anything under `security-governance/`, `experience-api-engagement/src/nexus_experience/auth.py`, the pipeline connectors, or the subprocess wiring in `src/nexus/` — get an additional review pass and may take longer.

---

## Adding a dependency

Nexus stays deliberately light: most of it runs on the standard library. Before adding a runtime dependency:

1. Explain the use case in the PR description.
2. Check whether the standard library or an existing dependency already covers it.
3. **Confirm the license is permissive and compatible with Apache-2.0.** MIT, BSD-2/3, Apache-2.0, ISC, and PSF are fine. **Copyleft licenses (GPL, AGPL, LGPL) must not be added as required runtime dependencies** — they may only appear behind an optional extra, and must be documented in `NOTICE`.
4. Pin a sensible floor (`cryptography>=42.0.0`); avoid capping the upper bound without a known incompatibility.
5. Add it to `NOTICE` with its name and license.

---

## Questions

- **How do I use Nexus?** → [SUPPORT.md](SUPPORT.md)
- **I found a security issue** → [SECURITY.md](SECURITY.md)
- **How is this governed?** → [MAINTAINERS.md](MAINTAINERS.md)
- **Anything else** → [open a discussion](https://github.com/Veloxs-ai/nexus/discussions)
