---
title: Repo-Tuned QA Workflow Template
impact: HIGH
impactDescription: produces a ready-to-copy GitHub Actions caller workflow whose setup steps actually install this repo, stack by stack
tags: ci, github-actions, setup-script, build-context, monorepo
---

## Repo-Tuned QA Workflow Template

`/build-context` writes `.qa/github-action-qa-pipeline-template.yml`: the generic caller workflow (`templates/qa-caller-workflow.yml`) with its setup filled in for **this** repo. A developer copies it to `.github/workflows/qa.yml` and only chooses the settings (`live`, `fix_bugs`, `model`, `effort`, …).

`/build-context` has no Bash, so nothing here can be run to check it. Every line is derived from files in the repo, and each setup line carries a short comment naming the file it came from, so a reviewer can check it at a glance. **Never invent a command the repo's files don't support.**

### 1. Start From the Generic Template, Change Only Four Things

Read `${CLAUDE_PLUGIN_ROOT}/templates/qa-caller-workflow.yml` and copy it **verbatim**, apart from:

1. **The header comment** (everything before `name:`). Replace it with the header in §6.
2. **`setup_script`** and the "Other examples" comment block after it. Replace both with the derived script (§3), followed by the dependency note that ends that block in the generic template (the "Test libraries must already be in the repo's own manifest…" lines).
3. **Version lines** `node_version`, `java_version`, `python_version`: uncomment and set the ones this repo needs (§4). Leave the others commented.
4. **`max_turns`**: uncomment it as `200` for a multi-stack repo or one with more than ~150 source modules. Otherwise leave it commented.

Everything else stays byte-for-byte: triggers, `uses:` and `plugin_ref` (keep them equal), `live: false`, and the commented `fix_bugs`, `clickup_branch_naming`, `model` and `effort` lines with their explanations. Those are the developer's choices, and the file must offer them exactly as the generic template does. In particular, never uncomment `model` or `effort`: the pipeline's defaults (`opus`, `high`) are what make a CI run as thorough as a local one.

### 2. Find the Stacks

Use the same stack split `/generate-tests` uses. If `.qa/test-inventory.json` has a `stacks` object, use those names and folders. Otherwise find every manifest tree (`pyproject.toml`, `requirements*.txt`, `package.json`, `pom.xml`, `build.gradle(.kts)`, `go.mod`) outside `node_modules`/`vendor`/build output.

- A JS **workspace** (`workspaces` in the root `package.json`, `pnpm-workspace.yaml`) is **one** install at its root, even if each package has its own `package.json`.
- A **multi-module Maven/Gradle** build is one install at the directory with the root `pom.xml` / `settings.gradle(.kts)`.
- The repo's own CI (`.github/workflows/*.yml`) is the best evidence of how it installs: the versions in `setup-node`/`setup-java`/`setup-python`, `npm ci` vs `pnpm install`, extra steps like code generation. Prefer what it does when it agrees with the manifests. If a workflow already calls `qa-pipeline.yml`, its `setup_script` is known to work; reuse it unless the manifests show it's stale (for example, it installs a file that no longer exists).

### 3. Setup Commands per Stack

Write one block per stack, headed by a comment line `# <folder>/ — <language>, <how it was decided>`. For a stack in a subfolder, use the tool's directory flag (`--prefix`, `--dir`, `--directory`, `-f`) or a subshell `(cd frontend && …)`, never a bare `cd`, which would leak into the next stack's lines. Start the script with `set -euo pipefail` on its own line, so a failed install stops the run with a clear error instead of running tests against a half-installed repo.

**Python**: the runner always has `python`/`pip`. Start with `python -m pip install -U pip`.

| Evidence | Install |
|---|---|
| `uv.lock` | `pip install uv`, `uv sync --frozen --directory <dir>`, then put the venv on the PATH for later steps: `echo "$PWD/<dir>/.venv/bin" >> "$GITHUB_PATH"` |
| `poetry.lock` | `pip install poetry`, `poetry config virtualenvs.create false`, `poetry install --no-interaction --directory <dir>` |
| `Pipfile.lock` | `pip install pipenv`, `(cd <dir> && pipenv install --dev --system --deploy)` |
| `requirements*.txt` | `pip install -r <dir>/requirements.txt`, plus the dev/test file if one exists (`requirements-dev.txt`, `requirements-test.txt`, `requirements/dev.txt`) |
| only `pyproject.toml` | `pip install -e "<dir>[dev]"` when an optional-dependencies group named `dev`/`test` exists (use its real name); `pip install --group <dir>/pyproject.toml:<name>` for a PEP 735 `[dependency-groups]` group; else `pip install -e <dir>` |

Then, **if `pytest` or `pytest-cov` appears in none of the dependency lists**, add `pip install pytest pytest-cov` (for uv: `uv pip install --python <dir>/.venv pytest pytest-cov`). Installing in CI is fine; only the repo's manifests are off-limits.

**JavaScript / TypeScript**:

| Evidence | Install |
|---|---|
| `package-lock.json` | `npm ci --prefix <dir>` |
| `pnpm-lock.yaml` | `corepack enable`, `pnpm --dir <dir> install --frozen-lockfile` |
| `yarn.lock` with `.yarnrc.yml` (Yarn 2+) | `corepack enable`, `(cd <dir> && yarn install --immutable)` |
| `yarn.lock` without `.yarnrc.yml` (Yarn 1) | `corepack enable`, `(cd <dir> && yarn install --frozen-lockfile)` |
| no lockfile | `npm install --prefix <dir> --no-audit --no-fund`, with a comment that there's no lockfile, so installs aren't reproducible |
| `bun.lock` / `bun.lockb` | The pipeline doesn't set up Bun. Write the placeholder in §5 |

Then, as each applies:

- **Prisma** (`prisma` in the dependencies): generate the client the tests import: `(cd <dir> && npx prisma generate)`, `pnpm --dir <dir> exec prisma generate`, or `(cd <dir> && yarn prisma generate)`.
- **Playwright or Cypress** in the dependencies: put `export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` / `export CYPRESS_INSTALL_BINARY=0` **before** the install. Unit tests never need the browsers, and downloading them costs minutes.
- **Vitest with no coverage provider** (`@vitest/coverage-v8` or `-istanbul` absent): add a commented-out line the developer can enable, `# npm install --prefix <dir> --no-save @vitest/coverage-v8@<the installed vitest version>`, with a comment that coverage is reported as unavailable until they do.

**Java / Kotlin**: the runner has Maven and Gradle; `java_version` (§4) sets the JDK.

| Evidence | Install (downloads dependencies and compiles the tests once, so a broken build fails here, clearly) |
|---|---|
| `mvnw` | `chmod +x <dir>/mvnw`, `(cd <dir> && ./mvnw -B -q test-compile)` |
| `pom.xml` without wrapper | `mvn -B -q -f <dir>/pom.xml test-compile` |
| `gradlew` | `chmod +x <dir>/gradlew`, `(cd <dir> && ./gradlew --no-daemon -q testClasses)` |
| `build.gradle(.kts)` without wrapper | `(cd <dir> && gradle --no-daemon -q testClasses)` |

**Go:** `(cd <dir> && go mod download)`.

### 4. Versions

Set a version only from evidence, and say where it came from in a trailing comment (`node_version: '20'   # from frontend/.nvmrc`):

| Input | Evidence, in order | If none |
|---|---|---|
| `node_version` | `.nvmrc`, `.node-version`, `.tool-versions`, `package.json` `volta.node`, the repo's CI `setup-node`, `engines.node` (the newest major it allows) | `'22'`, commented as a default (set only when the repo has JS/TS) |
| `java_version` | Gradle `jvmToolchain(N)` / `JavaLanguageVersion.of(N)`, Maven `<maven.compiler.release>` / `<release>` / `<java.version>`, `.java-version`, `.sdkmanrc`, the repo's CI `setup-java` | `'21'`, commented as a default (set only when the repo has Java/Kotlin) |
| `python_version` | `.python-version`, the repo's CI `setup-python`, `requires-python` / Poetry's `python` (the newest minor it allows) | leave the line commented; the pipeline defaults to 3.12 |

Pass the major version as a quoted string (`'21'`, not `21` or `21.0.2`).

### 5. When You Can't Work It Out

For a stack whose install can't be derived (an unknown package manager, Bun, a stack with no manifest), write a line that **fails loudly** rather than one that quietly installs the wrong thing:

```yaml
        # bff/ — could not work out how to install this stack (bun.lock: the pipeline does not set up Bun)
        echo "Agentic QE: replace this line with the commands that install bff/" >&2; exit 1
```

Say on screen which stack it was, and why.

### 6. Header

```yaml
# Agentic QE: QA pipeline workflow tuned for this repo.
#
# Generated by /agentic-qe:build-context from the repo's manifests (sha <context_sha>).
# To use it: copy this file to .github/workflows/qa.yml. Then review STEP 1, and
# choose your settings in STEP 2 (live, fix_bugs, model, effort, ...) in that copy.
#
# Don't edit this file: it is regenerated whenever the repo's setup changes.
# Stacks found: backend/ (Python, uv), frontend/ (TypeScript, Next.js, pnpm)
# Full guide: README, "Run it as a GitHub Action".
```

`<context_sha>` is the same SHA stamped into `.qa/context.md`. List every stack with its folder, language, framework (if any) and package manager or build tool.

### 7. Example: Two Stacks

```yaml
      setup_script: |
        set -euo pipefail
        # backend/ — Python, uv.lock → uv
        python -m pip install -U pip
        pip install uv
        uv sync --frozen --directory backend
        echo "$PWD/backend/.venv/bin" >> "$GITHUB_PATH"
        # frontend/ — TypeScript (Next.js), pnpm-lock.yaml → pnpm
        export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1   # @playwright/test in frontend/package.json
        corepack enable
        pnpm --dir frontend install --frozen-lockfile
        pnpm --dir frontend exec prisma generate    # prisma in frontend/package.json

      # Test libraries must already be in the repo's own manifest (jest/vitest,
      # @testing-library/*, junit-jupiter, mockito/mockk...). The pipeline never
      # adds dependencies; it reports the ones it needed and could not find.

      # ── STEP 2: settings (the defaults are right for a first run) ───────────
      plugin_ref: main         # same version as the @main in `uses:` above
      live: false              # false = report only. Set to true later to file real issues and PRs
      node_version: '20'       # from frontend/.nvmrc
      # java_version: '21'     # uncomment if the repo has Java or Kotlin (match the build's target)
      python_version: '3.11'   # from backend/.python-version
```

…and in the optional block, `max_turns: 200   # two stacks` is uncommented.

### Checklist

- [ ] Copied from the current generic template; only the header, `setup_script` (plus its examples block), version lines and `max_turns` changed
- [ ] One commented block per stack, using directory flags or subshells, with `set -euo pipefail` first
- [ ] Every command and version traced to a file in the repo, named in a comment
- [ ] Test runner/coverage plugin installed in CI when the repo's manifests lack them; manifests themselves untouched
- [ ] Underivable stacks get a failing placeholder, never a guess
- [ ] `live: false`, and the `fix_bugs`/`model`/`effort`/`clickup_branch_naming` options present, still commented, exactly as in the generic template
