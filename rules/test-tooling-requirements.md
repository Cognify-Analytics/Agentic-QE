---
title: Test Tooling Requirements
impact: HIGH
impactDescription: tells a developer exactly which test tools their repo is missing, in which version, and how to add them, before a pipeline run fails on it
tags: context, setup, dependencies, versions, powershell, build-context
---

## Test Tooling Requirements

Section 5 of `.qa/context.md` lists, per stack, what the QA pipeline needs in the repo to generate, run and measure tests. It shows what's present and what's missing, the version that fits **this** repo, and the exact steps to add it. The pipeline never installs into or edits a repo's manifests (`rules/general/compilation-verification.md`), so this section is the only place a developer learns what to add.

### 1. Sources, in Order of Authority

1. **`tooling_gaps` in `.qa/test-inventory.json`.** Gaps `/generate-tests` and `/triage-tests` actually hit at runtime: a command that failed, a module skipped for a missing package. These are confirmed. Always list them.
2. **Lockfiles**, for what's installed and at which exact version: `package-lock.json` (`"node_modules/<pkg>": { "version" }`), `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock`, `Pipfile.lock`.
3. **Manifests**, for declared ranges and the framework in use: `package.json`, `pyproject.toml`, `requirements*.txt`, `pom.xml` (including a Spring Boot parent or BOM, which manages test versions), `build.gradle(.kts)`, `gradle/libs.versions.toml`.
4. **Config:** `vitest.config.*`/`jest.config.*` (environment, coverage provider), Surefire's version and `argLine`, Gradle's `useJUnitPlatform()`.

`/build-context` can't run anything, so it never claims a tool *works*. It reports what the files show. A tool declared in the manifest but absent from the lockfile is ❓, not ✅.

### 2. What Each Stack Needs

"Required" means the pipeline fails or produces nothing without it. "When" items apply only if the condition holds in this repo; don't list them otherwise.

**Python (pytest)**

| Tool | Needed | Version rule |
|---|---|---|
| `pytest` | Required | A release that supports the repo's Python (`requires-python`). pytest 8.4+ needs Python 3.9+ |
| `pytest-cov` | Required for coverage | Latest release that supports the repo's Python |
| `pytest-asyncio` | When source has `async def` | A release whose own `pytest` requirement accepts the installed pytest |
| `pytest-django` | When Django is a dependency | Latest release supporting the installed Django |
| `pytest-mock` | When existing tests use the `mocker` fixture | Any current release |

**JavaScript / TypeScript**

| Tool | Needed | Version rule |
|---|---|---|
| `vitest` or `jest` | Required (one runner) | Already present, or the gap is "no test runner"; don't pick one for them, list both options |
| `@vitest/coverage-v8` (or `-istanbul`) | Required for coverage under Vitest | **Exactly the installed `vitest` version.** A mismatch fails at startup |
| `jest-environment-jsdom` | When Jest tests components (React/Next.js) | **Same major as `jest`** (Jest 28+ no longer bundles it) |
| `jsdom` (or `happy-dom`) | When Vitest tests components | A release whose `engines.node` accepts the repo's Node version |
| `ts-jest`, or `babel-jest` + `@babel/preset-typescript` | When Jest runs TypeScript and `next/jest`/`@swc/jest` isn't used | `ts-jest`: a release whose peer range includes the installed `jest` (same major) |
| `@types/jest` | When Jest + TypeScript use globals | Same major as `jest` |
| `@testing-library/react` | When React components are tested | React 19 → 16.1+; React 18 → 14.x or 16.x; React 17 → 12.x |
| `@testing-library/dom` | With `@testing-library/react` 16+ | 10.x (a required peer since RTL 16) |
| `@testing-library/user-event` | Recommended with RTL | 14.x |
| `@testing-library/jest-dom` | Recommended with RTL | 6.x (Vitest: imported as `@testing-library/jest-dom/vitest`) |
| `supertest` (+ `@types/supertest`) | When Express/Koa routes are tested and the repo has none | Latest |

**Java / Kotlin**

| Tool | Needed | Version rule |
|---|---|---|
| JUnit 5 (`junit-jupiter`) | Required | With Spring Boot: `spring-boot-starter-test`, **no version** (Boot manages it). Otherwise `org.junit:junit-bom` 5.10+ |
| Mockito (`mockito-core`, `mockito-junit-jupiter`) | Required for Java unit tests with collaborators | Boot-managed, or Mockito 5.x (needs Java 11+; Java 8 → 4.x) |
| AssertJ (`assertj-core`) | Recommended | Boot-managed, or 3.x |
| Maven Surefire | Required (Maven) | **3.x** (2.22.0 is the minimum that runs JUnit 5; older ones silently run 0 tests) |
| Gradle `useJUnitPlatform()` | Required (Gradle + JUnit 5) | A build change, not a dependency |
| Surefire `argLine` with `@{argLine}` | Required for coverage when the pom sets `argLine` | A build change |
| `spring-security-test` | When Spring Security is a dependency | Boot-managed |
| MockK | Recommended for Kotlin | A release supporting the repo's Kotlin version |
| `kotlinx-coroutines-test` | When Kotlin source uses coroutines | **Exactly the `kotlinx-coroutines-core` version** |
| `mockito-kotlin` | Kotlin with Mockito but no MockK | 5.x for Mockito 5 |
| `springmockk` | Optional: Spring + MockK slices | 4.x for Spring Boot 3 |

JaCoCo needs **no** repo change: the pipeline calls it from the command line (`rules/lang/jvm/jvm-build-and-location.md` §5). Only list it when `tooling_gaps` shows the JaCoCo version couldn't instrument the JDK.

**Runtimes:** list the Node, Python or JDK version each stack needs, derived exactly as `rules/qa-workflow-template.md` §4 does, so section 5 and the workflow template always agree.

### 3. Deriving the Version to Recommend

- **Pinned to another package** (`@vitest/coverage-v8` = `vitest`, `kotlinx-coroutines-test` = `kotlinx-coroutines-core`): give the exact version from the lockfile, e.g. `3.2.4`.
- **Same major as another package** (`jest-environment-jsdom`, `ts-jest`, `@types/jest`): give `^<major>`, e.g. `^29`.
- **Managed by a BOM or parent** (Spring Boot): say "no version — managed by Spring Boot <version>".
- **Constrained by a runtime or a peer** (pytest by Python, RTL by React): give the range from §2 and the verification command from §5.
- **No lockfile, only a range:** give the range and mark the row ❓.

Never recommend a version that conflicts with what's installed. When unsure, give the range plus the command that checks it, rather than a guessed exact version.

### 4. Section 5 Format

````markdown
## 5. Test tooling requirements
What the QA pipeline needs in this repo. ✅ present · ❌ missing · ⚠️ needs a change · ❓ couldn't tell from the files.
The pipeline never installs these itself. Add them once, commit the manifest and lockfile, and every later run (local and CI) has them.

### frontend/ — TypeScript · Vitest · React
| Needed | For | Version for this repo | Status |
|---|---|---|---|
| Node.js | everything | 20 (frontend/.nvmrc) | — |
| vitest | running tests | 3.2.4 | ✅ |
| @vitest/coverage-v8 | coverage numbers | 3.2.4 (must equal vitest) | ❌ coverage run failed without it |
| jsdom | component tests | latest supporting Node 20 | ❌ |
| @testing-library/react | component tests | 16.x (React 19) | ✅ 16.3.0 |
| @testing-library/dom | peer of RTL 16 | 10.x | ❌ |

**Fix (Windows PowerShell)**, from the repo root:
```powershell
Set-Location frontend
npm install --save-dev "@vitest/coverage-v8@3.2.4" "jsdom" "@testing-library/dom@^10"
Set-Location ..
```
**macOS / Linux / Git Bash:**
```bash
npm --prefix frontend install --save-dev @vitest/coverage-v8@3.2.4 jsdom "@testing-library/dom@^10"
```
Then commit `frontend/package.json` and `frontend/package-lock.json`.
````

- **One subsection per stack**, headed `### <folder>/ — <language> · <runner> · <framework>`. A single-stack repo uses one subsection named after the project.
- **Every row has a reason in "For"**, and a ❌ that came from `tooling_gaps` says what actually failed ("coverage run failed without it", "3 component modules skipped").
- **Fix steps only for ❌/⚠️ rows**, as **one** command per stack per platform that adds everything missing at once. Use the package manager the lockfile names (`npm`, `pnpm add -D`, `yarn add -D`, `uv add --dev`, `poetry add --group dev`, `pip install` + the requirements file to update).
- **Java/Kotlin have no install command:** give the exact `pom.xml` / `build.gradle(.kts)` snippet in the build's own DSL, then the PowerShell and bash commands that verify it (`.\mvnw.cmd -q test-compile` / `./mvnw -q test-compile`).
- **Nothing missing:** keep the table and replace the fix steps with "Nothing to install."
- **Optional or recommended tools** that are missing get ⚠️ only if a test the pipeline would write needs them. Otherwise list them under one "Optional:" line, not in the table.
- **600 words at most**, counted separately from the 1,500-word limit on the rest of the file. Never drop a ❌ row to fit; shorten the "For" texts instead.

### 5. PowerShell: What Breaks When Commands Are Copied from Bash

Write the PowerShell blocks so they paste and run as-is in Windows PowerShell 5.1 and PowerShell 7:

| Problem | Write it like this |
|---|---|
| `@` and `{ }` are PowerShell syntax (splatting, hashtables, script blocks), and version ranges can contain characters it reads specially | Quote every package spec: `"@vitest/coverage-v8@3.2.4"`, `"jsdom@^26"`. Quoting is harmless and removes the ambiguity |
| `>` and `<` are redirection, so `pip install pytest-cov>=5` writes a file called `=5` | Quote specifiers: `"pytest-cov>=5"` (in bash too) |
| `-Dname.with.dots=value` is split at the dots | Quote it: `"-Dtest=OrderServiceTest"` |
| Windows PowerShell 5.1 has no `&&` | One command per line, or `;` |
| `./mvnw` and `./gradlew` are shell scripts | `.\mvnw.cmd`, `.\gradlew.bat` |
| `npm.ps1 cannot be loaded because running scripts is disabled` | `npm.cmd install ...`, or once per user: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `VAR=value command` | `$env:VAR = "value"; command` |
| Python | `py -m pip install ...` (the Python launcher); a venv is activated with `.\.venv\Scripts\Activate.ps1` |

Verification commands to offer when a version is a range:

| Ecosystem | PowerShell | bash |
|---|---|---|
| npm | `npm view "@testing-library/react@16" peerDependencies` | `npm view @testing-library/react@16 peerDependencies` |
| pip | `py -m pip index versions pytest` | `python -m pip index versions pytest` |
| Maven | `.\mvnw.cmd dependency:tree "-Dincludes=org.mockito"` | `./mvnw dependency:tree -Dincludes=org.mockito` |
| Gradle | `.\gradlew.bat dependencies --configuration testRuntimeClasspath` | `./gradlew dependencies --configuration testRuntimeClasspath` |

### Checklist

- [ ] Every stack has a subsection; runtimes match the workflow template's versions
- [ ] Every `tooling_gaps` entry from the inventory appears as ❌ or ⚠️ with what actually failed
- [ ] Versions follow §3: exact when pinned, same major when tied, BOM-managed with no version, a range plus a check when constrained
- [ ] Fix steps: PowerShell first, then bash; one command per stack; scoped packages and specifiers quoted
- [ ] Java/Kotlin fixes are manifest snippets plus a verify command
- [ ] Section 5 at most 600 words
