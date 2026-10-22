# PRD — Agentic QE - Claude Code Skill

**Version:** 1.2
**What we are building:** A set of Claude Code skills that write unit tests, document a codebase, run the tests, and decide what each failure means.
**Where it runs:** Entirely inside Claude Code. No server. No hosted service.

---

## 0. Read this first (instructions for Claude Code)

You are building this project. Read the whole document before writing any file.

Build it as a **local project**, not a plugin. Skills go in `.claude/skills/` so they load straight away with no install step. We package it as a plugin only at the very end, once everything works.

**Do this before Phase 1, and then stop:**

```
1. Clone https://github.com/mavka-ai/unit-tests-skills into reference/mavka/
2. Read reference/mavka/LICENSE. Tell me whether we are allowed to reuse
   the rule files. If we are not, STOP and tell me before doing anything else.
3. Read every file in reference/mavka/skills/generate-tests/rules/
4. Write reference/MAVKA-AUDIT.md. For each rule file, give me:
   - a two-line summary
   - whether it is LANGUAGE-AGNOSTIC or JAVA-SPECIFIC
   - your recommendation: REUSE / ADAPT / SKIP
5. Wait for me to review the audit.
```

Do not skip step 2. Do not start Phase 1 until I approve the audit.

Section 13 has open questions. Ask me — do not guess the answers.

---

## 1. The problem

Testing work has three parts. Existing tools only handle the first one.

**Part 1 — Writing tests.** Tools exist. They work reasonably well. But they need a person to point at a specific file and stay involved.

**Part 2 — Understanding the codebase.** No tooling. Anyone reviewing tests has to work out what the project does, what its data looks like, and what is already covered. They start from zero every time.

**Part 3 — Understanding failures.** No tooling, and this is the expensive one. When a test fails, it is either a badly written test or a real bug in the code. Existing tools assume it is always a bad test. They quietly change the test so it passes, leave a comment saying "this might be a bug", and move on.

That comment is where real defects disappear. **Part 3 is the reason this project exists.**

---

## 2. What we want

- Write tests that match how the repo already writes tests
- Work on a whole repo, not just one file at a time
- Keep a project context document and a test inventory in the repo, updated in place
- Tell the difference between a bad test and a real bug
- Fix only what is safe to fix, and hand everything else to a named person
- Work as one full pipeline, or as three separate commands

---

## 3. What we are not doing in v1.0

- Integration tests, end-to-end tests, performance tests
- Monorepos or multiple repos in one run
- Any interface other than the terminal
- Merging its own pull requests
- Changing production source code — this is a hard rule, see Section 9
  (a narrow, off-by-default opt-in exception was added later; see Section 9.1)

---

## 4. Who uses it

| Person | Command they run | What they want |
|---|---|---|
| Developer working on a feature | `/generate-tests src/orders.py` | Tests for the file they are on, right now |
| Developer new to a repo | `/build-context` | To understand what this codebase does |
| Reviewer | `/triage-tests` | To know which failures are real bugs |
| CI (no human) | `/test-pipeline` | Everything, unattended, with issues filed |

Every stage must work on its own. This is a requirement, not a bonus.

---

## 5. How it is built

### 5.1 Four skills

Everything is a Claude Code skill. There are no separate agent files.

The three working skills use `context: fork` in their frontmatter. Forking gives each one its own separate context window, so it behaves like its own agent. Because each is still a normal skill, a developer can also call it directly as a slash command. One file covers both uses.

The orchestrator is **not** forked. It runs in the developer's main session so they can watch what is happening.

```
/test-pipeline                    (orchestrator, not forked)
   │
   ├── calls /generate-tests      (forked — own context)
   ├── calls /build-context       (forked — own context)
   └── calls /triage-tests        (forked — own context)
```

### 5.2 Sequential, not parallel

For v1.0, `/generate-tests` handles modules **one after another**, not all at once.

Parallel workers would be faster, but they are harder to debug and harder to cap the cost on. Get the prompts right first. Fan-out is a v2 decision.

### 5.3 Two ways to run it

**Local (the normal case).** A developer runs the command in their own repo. Their dependencies are already installed. They get instant feedback and they approve the test list before code is written.

**CI (unattended).** A GitHub Action runs the same skills with no human. Same rules, same files, just no approval step.

```yaml
- uses: anthropics/claude-code-action@v1
  with:
    prompt: "/test-pipeline"
    claude_args: "--max-turns 40 --allowedTools Read,Write,Edit,Bash"
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Check the current action docs before finalising this — the syntax may have changed.

### 5.4 Our project layout

```
qa-pipeline/
├── .claude/
│   └── skills/
│       ├── generate-tests/SKILL.md    forked
│       ├── build-context/SKILL.md     forked
│       ├── triage-tests/SKILL.md      forked
│       └── test-pipeline/SKILL.md     orchestrator, not forked
├── rules/                             ONE copy only
│   ├── general/                       test rules, any language
│   ├── lang/<language>/               rules for one language
│   ├── error-classification.md        bad test vs real bug
│   ├── context-file-template.md       shape of the context document
│   └── test-location-map.md           where tests go, per language
├── templates/
│   └── github-issue-template.md
├── scripts/
│   ├── parse_coverage.py              coverage output → clean JSON
│   └── resolve_owners.py              file path → owner from CODEOWNERS
├── fixtures/
│   ├── sample-repo/                   test repo with known bugs
│   └── GROUND-TRUTH.md                the answer key
├── reference/
│   ├── mavka/                         cloned, read-only, gitignored
│   └── MAVKA-AUDIT.md
├── .github/workflows/qa-pipeline.yml
└── README.md
```

Rules live in exactly one folder. The reference repo keeps two copies and asks maintainers to sync them by hand. Do not copy that. Every skill points at `rules/`.

---

## 6. What we write into the user's repo

This is the most important design decision in the project. There are three kinds of output and they are treated differently.

### 6.1 `.qa/` — our folder, committed to the repo

We own exactly one folder in the user's repo. It is committed, so it survives between runs and everyone on the team shares it.

```
.qa/
├── context.md              what this project is, its schema, its architecture
├── github-action-qa-pipeline-template.yml   the CI caller workflow, setup filled in for this repo
├── test-inventory.json     what tests exist, coverage, when they were last touched
└── runs/                   optional history of past runs
    └── 2026-08-21-a1b2c3d.json
```

Why not `.claude/`: that folder belongs to Claude Code itself — skills, settings, commands. Putting our output there risks collisions and makes it unclear what is configuration and what is generated. `.qa/` is ours alone.

### 6.2 Tests — wherever the repo already puts them

**We never invent a test location.** Check in this order:

1. **Does the repo already have tests?** Use that location, even if it is unusual. The repo's convention beats the language default.
2. **No existing tests?** Use the language default:

| Language | Test location |
|---|---|
| Java / Kotlin (Maven, Gradle) | `src/test/java/` mirroring the package path |
| Python | `tests/` |
| Go | same folder as the source file, named `*_test.go` |
| JavaScript / TypeScript (Jest) | `__tests__/` or alongside as `*.test.ts` |
| C# | a sibling `<Project>.Tests/` project |
| Rust | `tests/` for integration, inline `#[cfg(test)]` for unit |

3. **Cannot tell?** Stop and ask the user. Do not guess.

Put this table in `rules/test-location-map.md`.

### 6.3 Test data — builders, not a data folder

Reusable test data is a good goal. A separate folder of static data files is the wrong way to get it — if the data lives far from the test, you have to open two files to understand one test.

Instead, generate builders where the framework expects them: `conftest.py` fixtures for pytest, factories for Jest, builder classes for Java. Check for existing helpers first and add to them rather than making duplicates.

Only exception: genuinely large fixtures — sample PDFs, big JSON payloads, CSV files. Those go in `tests/fixtures/`, which is already a normal convention.

### 6.4 `.claude-pipeline/` — scratch, gitignored

Working files that only matter during a single run. Deleted freely.

```
.claude-pipeline/
├── run.json               orchestrator writes
├── 01-tests.json          generate-tests writes
├── raw-test-output.txt    full test output, for debugging
├── 03-triage.json         triage-tests writes
└── summary.md             orchestrator writes, for humans
```

### 6.5 How skills pass information to each other

Forked skills cannot see each other's thinking. They only share files. **If a skill works something out and does not write it down, it is gone.**

```
generate-tests → writes .qa/test-inventory.json and 01-tests.json
build-context  → reads  .qa/test-inventory.json
               → writes .qa/context.md
triage-tests   → reads  .qa/context.md and 01-tests.json
               → writes 03-triage.json
orchestrator   → reads  all of them → writes summary.md
```

If a skill runs on its own and an input file is missing, it works out what it can and sets `"status": "partial"` with a note explaining what was missing. It must not crash. Because `.qa/` is committed, this is now rare — a developer can run `/triage-tests` on its own and the context file will usually already be there.

Every file records the git SHA it was made at. If `/triage-tests` sees that `context.md` was built at a different SHA, it warns that the context may be out of date and carries on with less confidence.

### 6.6 Updating in place, not rewriting

Both files in `.qa/` are updated, never regenerated from scratch, unless the user passes `--rebuild`.

**Context update check.** Compare the current SHA against `context_sha` in `context.md`. Look at what changed since then:

| What changed | What to do |
|---|---|
| Nothing | Skip. Say "context is current." |
| Schema files, models, migrations | Update section 2 only |
| README, docs | Update section 1 only |
| New modules or folders added | Update section 3 |
| Tests changed | Update section 4 from the inventory |
| More than 30% of files changed | Rebuild the whole document |

**Inventory update check.** Compare test files on disk against what the inventory records. Add new ones, remove deleted ones, refresh coverage numbers.

Every update appends a line to the changelog at the bottom of the file, so the team can see what changed and when.

---

## 7. The four skills

### 7.1 `/generate-tests [file or folder]`

```yaml
name: generate-tests
description: Use when the user asks to generate, create, or write unit tests
  for code, or to increase test coverage for a file or repository.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
context: fork
```

**Steps**

1. Read the rules in `rules/general/` and `rules/lang/<language>/`.
2. Work out the stack. Look at manifest files to find the language, the test framework, and the test command. If there is no test framework, say so and stop.
3. Work out where tests go, using the order in Section 6.2.
4. Read `.qa/test-inventory.json` if it exists. This tells you what already has tests without scanning the whole repo.
5. Pick what to test. If the user gave a target, use it. If not, list the modules with no tests and rank them — business logic and entry points first, config and simple data classes last. Take the top 20.
6. Read the dependencies. Follow the imports and read the actual types the target uses. **Do not skip this.** It is the difference between tests that compile and tests that invent method names.
7. Check for existing tests for this specific target. If a test file exists, read it and add to it — do not make a second file. If none exists, read 2–3 nearby test files to learn the house style.
8. Check for existing test data builders (`conftest.py`, factories, builder classes). Add to them rather than duplicating.
9. List the test cases in Given-When-Then form, naming which code branch each one covers. Name format: `{method}_{state}_{outcome}`.
10. Ask the user to approve the list. **Skip this step when running in pipeline mode.**
11. Write the test code, in the location from step 3.
12. Verify twice. First compile — up to 5 attempts. Then run — up to 3 fix attempts per test. If a test still fails after 3 attempts, delete it and say so.
13. Get coverage by running `scripts/parse_coverage.py`.
14. Update `.qa/test-inventory.json` and write `01-tests.json`.

**Limits:** 20 modules per run. 5 compile attempts. 3 fix attempts per test.

**Hard rules:**
- May only create or change files in the test location and its builders
- Never invents a test folder — follows Section 6.2

**Expected output — `.qa/test-inventory.json` (committed)**

```json
{
  "schema_version": 1,
  "last_updated": "2026-08-21T14:02:00Z",
  "last_updated_sha": "a1b2c3d",
  "language": "python",
  "framework": "pytest",
  "test_command": "pytest -q --cov=src --cov-report=xml",
  "test_location": "tests/",
  "coverage": {
    "total": 67.4,
    "measured_at_sha": "a1b2c3d"
  },
  "modules": [
    {
      "source": "src/orders.py",
      "test_file": "tests/test_orders.py",
      "test_count": 12,
      "coverage": 82.1,
      "generated_by_qa": true,
      "last_touched_sha": "a1b2c3d"
    },
    {
      "source": "src/users.py",
      "test_file": "tests/test_users.py",
      "test_count": 4,
      "coverage": 45.2,
      "generated_by_qa": false,
      "last_touched_sha": "9f8e7d6"
    },
    {
      "source": "src/legacy_sync.py",
      "test_file": null,
      "test_count": 0,
      "coverage": 0.0,
      "skipped_reason": "needs live network, cannot mock cleanly"
    }
  ],
  "builders": [
    { "file": "tests/conftest.py", "provides": ["order_factory", "customer_factory"] }
  ],
  "changelog": [
    "2026-08-21 a1b2c3d — added tests for orders, pricing; coverage 51.0 → 67.4",
    "2026-08-14 9f8e7d6 — initial inventory built"
  ]
}
```

The `generated_by_qa` flag matters: it tells us which tests we own and may edit, and which a human wrote and we should leave alone.

**Expected output — `.claude-pipeline/01-tests.json` (scratch)**

```json
{
  "status": "ok",
  "git_sha": "a1b2c3d",
  "language": "python",
  "framework": "pytest",
  "test_command": "pytest -q --cov=src --cov-report=xml",
  "test_location": "tests/",
  "files_created": ["tests/test_orders.py", "tests/test_pricing.py"],
  "files_modified": ["tests/test_users.py", "tests/conftest.py"],
  "coverage": { "before": 51.0, "after": 67.4 },
  "modules_skipped": [
    { "path": "src/config.py", "reason": "constants only, nothing to test" }
  ],
  "tests_removed": [
    { "test": "process_refund_partialAmount_updatesLedger",
      "reason": "could not be made to pass in 3 attempts" }
  ],
  "notes": "Matched existing pytest fixtures in tests/conftest.py."
}
```

**Also expected on screen (the test case list, before approval):**

```
## Test Cases for OrderService.createOrder

### 1. createOrder_validRequest_returnsOrderId
- Given: a valid OrderRequest with 2 line items
- When: createOrder is called
- Then: returns a non-null order ID and saves once to the repository
- Code branch: happy path, line 34

### 2. createOrder_emptyItems_throwsValidationError
- Given: an OrderRequest with an empty items list
- When: createOrder is called
- Then: throws ValidationError, repository is never called
- Code branch: validation guard, line 28
```

### 7.2 `/build-context [--rebuild]`

```yaml
name: build-context
description: Use when the user asks for a project context document, an
  architecture or schema overview, or documentation of what a repository does.
allowed-tools: Read, Write, Glob, Grep
context: fork
```

This is the most locked-down skill on purpose. No Bash. No Edit. It reads files and writes one document.

**Steps**

1. Read `rules/context-file-template.md`. The template fixes the shape of the output so every run looks the same.
2. Does `.qa/context.md` already exist?
   - **No** → build the whole thing.
   - **Yes, and `--rebuild` was passed** → build the whole thing.
   - **Yes** → run the staleness check in Section 6.6 and update only the sections that need it. If nothing changed, say "context is current" and stop.
3. Read `.qa/test-inventory.json`. Coverage numbers come from here. Never recalculate them.
4. Write the project summary. Read the README, `docs/`, the manifest description, and the folder layout. Cover what the project does, who uses it, and its main features.
5. Write the data schema. Look at migrations, `models/`, `schema.sql`, ORM definitions, type files. Cover the main entities, their key fields, and how they relate.
6. Write the architecture. Entry points, main modules, external services, environment variables.
7. Write the test section, using the numbers from step 3.
8. Add a changelog line at the bottom.
9. Save to `.qa/context.md`.

**Anything you worked out rather than read directly must be marked `[inferred]`.** Later stages need to know what is a fact and what is a guess.

**Limit:** 1,500 words. `/triage-tests` has to load this into its context.

**Expected output — `.qa/context.md` (committed)**

```markdown
# Project Context — order-service

<!-- Generated by qa-pipeline. Edited by hand? Add [manual] to any line
     you change and it will be preserved on the next update. -->

context_sha: a1b2c3d
last_updated: 2026-08-21

## 1. What this project does
An internal HTTP service that accepts customer orders, validates them
against inventory, and publishes confirmed orders to a payments queue.

Primary users: the storefront frontend and the mobile app. [inferred]
Main features: order creation, order cancellation, price calculation,
inventory reservation.

## 2. Data schema
**Order** — id (uuid, pk), customer_id (fk → Customer), status (enum:
DRAFT, CONFIRMED, CANCELLED), total_cents (int), created_at (timestamp)

**OrderItem** — id (uuid, pk), order_id (fk → Order), sku (string),
quantity (int), unit_price_cents (int)

**Customer** — id (uuid, pk), email (string, unique), tier (enum:
STANDARD, PREMIUM)

Relationships: one Order has many OrderItems. One Customer has many Orders.
Source: src/models/*.py and migrations/003_orders.sql

## 3. Architecture
Entry point: src/api/app.py (FastAPI)
Main modules: api/ (routes), services/ (business logic), models/ (ORM),
adapters/ (external calls)
External services: Postgres, Redis (inventory locks), SQS (payments queue)
Env vars: DATABASE_URL, REDIS_URL, PAYMENTS_QUEUE_URL, INVENTORY_API_KEY

## 4. Test coverage
Overall: 67.4%
Well covered: src/orders.py (82.1%), src/pricing.py (74.0%)
Weakly covered: src/users.py (45.2%)
Not covered: src/legacy_sync.py — needs live network
Framework: pytest, tests in tests/, shared builders in tests/conftest.py
Known gaps: no tests for the cancellation flow or the SQS adapter.

## Changelog
- 2026-08-21 a1b2c3d — updated schema (Customer.tier added), refreshed coverage
- 2026-08-14 9f8e7d6 — first version
```

Human edits are preserved. If a developer improves a line and marks it `[manual]`, the next update leaves it alone.

### 7.3 `/triage-tests` — the important one

```yaml
name: triage-tests
description: Use when the user asks to run tests and triage, classify, or
  fix failures, or to file issues for failing tests.
allowed-tools: Read, Edit, Glob, Grep, Bash
context: fork
```

**Steps**

1. Read `.qa/context.md`. This is the whole reason the previous stage exists — you cannot judge whether a failure is a bug unless you know what the code is supposed to do. If it is missing, warn and continue with less confidence. If its `context_sha` differs from the current SHA, warn that it may be out of date.
2. Get the test command from `.qa/test-inventory.json`, falling back to `01-tests.json`. Do not guess it.
3. Run the tests. Save the full output to `raw-test-output.txt`.
4. Pull out each failure: test name, file, error type, message, stack trace.
5. Read `rules/error-classification.md` and label each failure SIMPLE, COMPLEX, or AMBIGUOUS.
6. **If SIMPLE:** create a branch `auto-fix/triage-<sha>`. Make the smallest possible fix **to the test**. Re-run just that test. If it passes, keep it. If not, undo the change and relabel it COMPLEX. Maximum 2 attempts.
7. **If COMPLEX or AMBIGUOUS:** run `scripts/resolve_owners.py` to find the owner. Search existing open issues first. If a matching issue exists, comment on it instead of making a new one. Otherwise create an issue using the template, including the failure output, the relevant part of the context document, and an @mention for the owner.
8. If any fixes were made, open a pull request from the auto-fix branch.
9. Write `03-triage.json`.

**Only edit tests marked `generated_by_qa: true` in the inventory.** A human-written test that fails is never silently changed — it goes straight to COMPLEX.

**Classification rules (put these in `rules/error-classification.md`)**

| SIMPLE — fix the test | COMPLEX — file an issue |
|---|---|
| Import or module-not-found error | Assertion fails on business logic |
| Typo or syntax error in the test | Behaviour contradicts what the docs say |
| Wrong assertion method used | Timing or race condition |
| Missing or wrong fixture | Fixing it would mean changing source code |
| Obvious type mismatch in setup | Failure at an integration boundary |
| | The test was written by a human |

**AMBIGUOUS is always treated as COMPLEX. Never guess.**

**Limits:** 2 fix attempts per failure. Maximum 10 issues per run — beyond that, combine the rest into one summary issue. 30 turns.

**Expected output — `.claude-pipeline/03-triage.json`**

```json
{
  "status": "ok",
  "git_sha": "a1b2c3d",
  "context_sha": "a1b2c3d",
  "context_stale": false,
  "totals": { "tests": 84, "passed": 79, "failed": 5 },
  "classifications": [
    { "test": "test_create_order_valid",
      "file": "tests/test_orders.py",
      "type": "SIMPLE",
      "reason": "ImportError — OrderRequest imported from wrong module" },
    { "test": "test_apply_discount_premium_tier",
      "file": "tests/test_pricing.py",
      "type": "COMPLEX",
      "reason": "Premium tier discount returns 10%, context document says 15%. Looks like a real bug in src/pricing.py line 47." },
    { "test": "test_reserve_inventory_concurrent",
      "file": "tests/test_inventory.py",
      "type": "COMPLEX",
      "reason": "Passes alone, fails in the full suite. Likely a race condition on the Redis lock." }
  ],
  "fixes_applied": [
    { "test": "test_create_order_valid",
      "change": "corrected import path to src.models.order",
      "attempts": 1 }
  ],
  "pr_url": "https://github.com/acme/order-service/pull/412",
  "issues_created": [
    { "url": "https://github.com/acme/order-service/issues/288",
      "test": "test_apply_discount_premium_tier",
      "owners": ["@payments-team"],
      "reason": "suspected real bug in discount calculation" }
  ],
  "issues_commented": [
    { "url": "https://github.com/acme/order-service/issues/241",
      "test": "test_reserve_inventory_concurrent",
      "reason": "matches existing open flaky-test issue" }
  ],
  "escalated": [],
  "caps_hit": []
}
```

**Expected GitHub issue**

```
Title: [QA Pipeline] Premium tier discount may be incorrect

**Failing test:** test_apply_discount_premium_tier
**File:** tests/test_pricing.py
**Detected at:** a1b2c3d

**What happened**
Expected 15% discount for PREMIUM customers, got 10%.
  assert 8500 == 9000

**Why we think this is a real bug, not a bad test**
.qa/context.md records the premium tier as a 15% discount, taken from
docs/pricing.md. src/pricing.py line 47 applies 0.10. The test matches
the documented behaviour. The code does not.

**Suggested owner:** @payments-team (from CODEOWNERS: src/pricing.py)

**We did not change any code.** This needs a human decision about which
is correct — the documentation or the implementation.
```

### 7.4 `/test-pipeline`

```yaml
name: test-pipeline
description: Use when the user asks to run the full QA pipeline, audit test
  health end to end, or set up testing for a repository.
allowed-tools: Read, Write, Bash, Skill
```

Not forked. Runs in the main session so the developer can watch.

**Steps**

```
BEFORE STARTING
  check we are in a git repo — if not, stop
  create .qa/ if it does not exist
  create .claude-pipeline/
  write run.json with SHA, branch, timestamp, mode = pipeline
  make sure .claude-pipeline/ is in .gitignore
  make sure .qa/ is NOT in .gitignore — it is meant to be committed

STAGE 1  run /generate-tests
  CHECK: does 01-tests.json exist, and is status not "failed"?
  CHECK: has .qa/test-inventory.json been updated?
  if no → STOP and report

STAGE 2  run /build-context
  CHECK: does .qa/context.md exist and have content?
  if no → STOP and report

STAGE 3  run /triage-tests
  CHECK: does 03-triage.json exist?
  if no → STOP and report

FINISH
  read all of them, print a summary, save it to .claude-pipeline/summary.md
  copy the run record to .qa/runs/<date>-<sha>.json
  remind the developer to commit .qa/ along with the new tests
```

The checks between stages are the point. Without them, a silent failure in stage 1 gives stage 2 nothing to work with, and stage 3 then acts on a document full of nonsense.

**Expected output — `.claude-pipeline/summary.md`**

```markdown
# QA Pipeline Run — order-service
Started 2026-08-21 14:02 | SHA a1b2c3d | branch feature/refunds

## Tests
Created 2 new test files, added to 1 existing file.
Coverage 51.0% → 67.4%
1 test removed — could not be made to pass.

## Context
Updated 2 sections (data schema, test coverage). Full rebuild not needed.

## Failures
5 failed out of 84.
1 fixed automatically (import path).
2 raised as issues.
2 matched existing issues — commented instead.

## Needs a human
- Issue #288 — premium discount may be a real bug (@payments-team)
- Issue #241 — inventory race condition, commented on existing issue

## Changes made
PR #412 — one test import fix. Nothing merged. No source code changed.

## Please commit
  .qa/context.md
  .qa/test-inventory.json
  tests/test_orders.py, tests/test_pricing.py, tests/test_users.py
```

---

## 8. What ends up in the user's repo

After a run, the developer sees this in `git status`:

```
new file:   .qa/context.md
new file:   .qa/test-inventory.json
new file:   tests/test_orders.py
new file:   tests/test_pricing.py
modified:   tests/test_users.py
modified:   tests/conftest.py
```

And nothing else. `.claude-pipeline/` is ignored. No production source file is touched, ever.

---

## 9. Safety rules

These are not negotiable. Write them into every skill they apply to.

1. **Never change production source code.** If a fix needs a source change, that is automatically COMPLEX and becomes an issue. Without this rule the pipeline will "fix" failing tests by editing the source to match the bug.
2. **Never edit a human-written test.** Only tests marked `generated_by_qa: true` may be changed. Everything else is COMPLEX.
3. **Never invent a test folder.** Follow Section 6.2.
4. **Never write outside `.qa/` and the test location.**
5. **Never push to a main or default branch.** Fixes go to a branch, then a pull request.
6. **Never merge anything.** People merge.
7. **A suspected bug gets an issue, not a comment.** The reference tool leaves a `// might be a bug` note and moves on. That note is exactly the failure we are here to fix.
8. **Every limit is a hard stop** and gets recorded in `caps_hit`.
9. **In CI, keep the tool list small** and always set `--max-turns`.

---

## 9.1 Opt-in exception to Rule 1 — bug-fix mode (v1.2, off by default)

Rule 1 above is the default for this project and stays the default for
anyone who doesn't explicitly turn on `fix_bugs`. This section documents
the one deliberate, narrow exception, added at explicit user request after
v1.0 shipped: a team may opt in to having `/triage-tests` write an actual
fix to production source for a narrow class of COMPLEX bugs, verify it,
and open a **second, separate pull request** linked to the issue Rule 7
already produced — never merged by the pipeline (Rule 6 is untouched).

The point of this mode is to close the loop the rest of this document
deliberately leaves open: today, a real bug gets an issue and a human has
to write the fix from scratch. `fix_bugs` lets the pipeline hand that human
a candidate fix to review instead of a blank issue — without weakening any
of the guarantees Section 9 exists to provide.

Guardrails that make this a bounded exception rather than a reopening of
Rule 1 generally:

- **Off by default, explicit opt-in per run** (`--fix-bugs` / `run.json`'s
  `"fix_bugs"` field). Never inferred from context, never turned on by a
  missing field.
- **Narrow eligibility.** Only COMPLEX failures backed by a specific
  documented expectation — a `.qa/context.md` line, a docstring, or
  adjacent docs — that the code contradicts. Never timing/race conditions,
  never integration-boundary failures, never a human-written test, never
  an AMBIGUOUS failure. See `rules/error-classification.md`'s "Eligible
  for opt-in bug-fix mode?" column.
- **Scoped and capped.** Smallest possible change; abandoned if it would
  touch more than 2 files or any file the failure's own stack trace
  doesn't point to. 2 verification attempts. 3 bug-fix PRs per run.
- **Verified, not guessed.** Both the specific failing test and the whole
  stack's suite must pass clean before a PR is opened. An attempt that
  can't get there is undone completely and falls back to issue-only.
- **Never auto-closes its issue.** The PR says "Relates to #N", never
  "Fixes #N" — merging the PR is not the same event as a human deciding
  the bug is actually resolved, and GitHub's auto-close-on-merge keyword
  would conflate the two.
- **A second, clearly-labeled PR.** A bug-fix PR is never combined with
  the routine SIMPLE-test-fix PR (Section 7.3, Step 8) — a reviewer must
  be able to accept one without the other, since they carry different
  review burdens (a test typo vs. a production behavior change).
- **Requires stronger branch protection on the adopting repo** — required
  human approval before merge, not just "require a PR." See README, "Set
  it up in a target repo."

Mechanically, this lives in `skills/triage-tests/SKILL.md` as Step 7.5
(attempt and verify the fix) and Step 8.5 (open the PR and cross-link it to
the issue), and in `templates/bug-fix-pr-template.md` for the PR body
itself. `.claude-pipeline/03-triage.json` gains a `bug_fix_prs_created`
array alongside `issues_created`.

---

## 10. Build order

| Phase | What gets built | Finished when |
|---|---|---|
| 0 | License check, `MAVKA-AUDIT.md` | I approve the audit |
| 1 | `rules/`, `test-location-map.md`, fixture repo, `/generate-tests` | Produces passing tests in the right folder and a valid `.qa/test-inventory.json` |
| 2 | `/triage-tests`, `error-classification.md` | 80% or better on the fixture answer key |
| 3 | `/build-context`, template, incremental update logic | Two runs at the same SHA give the same document; second run correctly says "context is current" |
| 4 | `/test-pipeline`, GitHub Action | Full run works; checks proven by deliberately breaking stage 1 |
| 5 | Plugin packaging | Installs cleanly from the private repo on a fresh machine |

Stage 3 is built after stage 2 even though it runs before it. Triage is the risky part and the part that makes this product worth building — prove it early. Context-building is the most predictable, so it can wait.

---

## 11. The test fixture (build this in Phase 1)

Create `fixtures/sample-repo/` with a small set of modules. Some contain deliberate **real bugs** — an off-by-one, a wrong boundary condition, bad null handling. Others are correct. Keep the answers in `fixtures/GROUND-TRUTH.md`.

Also include a couple of **human-written tests** so we can check the tool leaves them alone.

Phase 2 is not finished until triage results are graded against that answer key.

Both kinds of mistake matter, but one is far worse: **a real bug labelled SIMPLE and quietly "fixed" is the failure this whole project exists to prevent.** That number must be zero.

---

## 12. Done when

- [ ] All three skills run on their own and produce valid output with no scratch files present
- [ ] `.qa/context.md` and `.qa/test-inventory.json` are created, committed, and updated in place on the next run
- [ ] A second run with no code changes reports "context is current" and does not rewrite the document
- [ ] Human edits marked `[manual]` survive an update
- [ ] Tests are written to the repo's existing location, or the correct language default
- [ ] `/test-pipeline` runs all three and stops correctly when stage 1 is deliberately broken
- [ ] Triage is 80%+ accurate on the fixture, with zero real bugs auto-fixed
- [ ] No human-written test was modified
- [ ] No run changed production source code or pushed to a default branch
- [ ] Rules exist in one folder only
- [ ] All limits are enforced and recorded
- [ ] The GitHub Action completes a run end to end with no human involved

---

## 13. Questions for me — ask, do not guess

1. Which language and test framework are we targeting first?
2. GitHub access through the `gh` CLI or the GitHub MCP server?
3. Does the target repo have a CODEOWNERS file? If not, who should issues go to?
4. What coverage percentage counts as good enough?
5. On the first CI run against an old repo, should it file issues straight away or just report?
6. Should the CI run trigger on every pull request, or nightly?
7. Should the pipeline commit `.qa/` itself, or leave it staged for the developer to commit?

---

## Decisions log (resolved outside this document)

- **Q1 (language/framework):** No single language is hardcoded. `/generate-tests` detects the target repo's language from its manifest files and generates tests in that language, per the Section 6.2 table. The Phase 1 fixture repo (`fixtures/sample-repo/`) is Python/pytest, matching this PRD's own worked examples.
- **Language depth beyond Python:** `rules/lang/javascript/` (JS and TS together: Jest/Vitest/`node:test`, mocking, TypeScript, location) with `frameworks/` for React, Next.js and Node backends, and `rules/lang/jvm/` (Maven/Gradle, location, JaCoCo/Kover coverage, Spring Boot under `frameworks/`) shared by `rules/lang/java/` (JUnit 5, AssertJ, Mockito, builders) and `rules/lang/kotlin/` (JUnit 5/Kotest, MockK, coroutines). `/generate-tests` loads the language folder(s) as Tier 1, and a `frameworks/` file only when the stack depends on that framework (Tier 1b), so a Python run reads nothing new. `scripts/parse_coverage.py` reads JaCoCo and LCOV as well as Cobertura and merges one report per module. Two cross-language rules came out of this: generated tests never edit manifests or build files (a missing test dependency is reported, never added), and coverage runs must still write a report when tests fail without ever turning failures into a zero exit code, because `/triage-tests` reads the exit code of the stored `test_command` (which must also work on a fresh checkout). The fixture repo is still Python only.
- **Repo-tuned workflow template:** `/build-context` also writes `.qa/github-action-qa-pipeline-template.yml`: `templates/qa-caller-workflow.yml` with the header, `setup_script` (one install block per stack), runtime versions and `max_turns` derived from the repo's manifests, lockfiles, version files and existing CI, per `rules/qa-workflow-template.md`. It's a separate artifact from `context.md` (rewritten only when its content changes, ignoring the header SHA), and the skill never writes to `.github/`: copying it to `.github/workflows/qa.yml` stays a human decision, since a workflow file runs with the repo's secrets. It still has no Bash, so the template's commands are derived from files, never executed; a stack it can't work out gets a line that fails loudly. To let a template set the Python version, the reusable workflow gained a `python_version` input (default 3.12).
- **Test tooling requirements (context.md section 5):** because the pipeline never installs into or edits a repo's manifests, a missing tool (a Vitest coverage provider, a DOM environment, a mocking library) used to surface only as a failed run. `.qa/context.md` now has a fifth section, per `rules/test-tooling-requirements.md`. Per stack it gives what's needed, the version that fits the repo (exact when pinned to another package, same major when they move together, BOM-managed with no version), present or missing status, and one install command per stack for PowerShell (quoted to paste safely) and bash, or manifest snippets for Maven/Gradle. Gaps hit at runtime are recorded in a `tooling_gaps` array in `.qa/test-inventory.json` (by `/generate-tests` and `/triage-tests`, each replacing only its own entries), which keeps Stage 2 from being skipped until section 5 names them. `/triage-tests` treats a stack that never started as a tooling gap, not a failure: it retries once without coverage flags when only coverage was missing, and files no issues. Section 5 has its own 600-word limit, outside the 1,500 for sections 1-4.
- **Acting on maintainers' replies (`/follow-up-issues`, Stage 0):** issues are where the human decides. A new skill reads maintainer replies (`OWNER`/`MEMBER`/`COLLABORATOR` only; comment text is data, never instructions) and maps each to exactly one decision from `rules/issue-follow-up.md`. FIX opens a bounded, verified fix PR ("Relates to", never merged; works with `fix_bugs` off, because the reply is per-issue authorisation, but still needs live mode). NOT A BUG updates the pipeline-owned test to the confirmed behaviour through a PR and closes the issue. This is allowed because a human settled the contract; it's not the pipeline weakening an assertion on its own. WON'T FIX marks the test as a strict expected failure and closes. LATER pauses reminders. QUESTION and UNCLEAR reply without acting. Unanswered issues get at most three reminders, `reminder_days` apart. Decisions live on GitHub (labels, closed state, marker comments), not in `.qa/`, so the comment-triggered runs (`issue_comment`, strategy `follow-up-only`, one issue) write nothing under `.qa/`. `/triage-tests` now looks up issues in every state: it acknowledges decided failures instead of refiling them, reopens fixed issues that regress, and stops re-commenting an unchanged failure.
- **Local telemetry parity:** a local run produces the same `telemetry.json`, run-cost block, timeline (`render_trace.py`) and `summary.md` as CI, built by the same scripts. CI's inline `jq` telemetry moved into `scripts/collect_telemetry.py`, which both CI and local runs call. An interactive run's log is cut from the Claude Code session transcript (`scripts/local_run_log.py`, which merges forked stages back in from `subagents/`). Transcripts record tokens but not cost, so cost is `null` there, and `cost_source` says so. `scripts/run_local.py` runs the pipeline headless exactly as CI does, for exact cost. `telemetry.json` gained `source`, `cost_source` and `model_used`; every existing field keeps its meaning.
- **Q2 (GitHub access):** Try the GitHub MCP server first; fall back to the `gh` CLI if MCP is not configured/available.
- **GitHub writes during development (Phase 1–4):** `/triage-tests` defaults to report-only — it computes classifications and fixes locally and writes out what it *would* create (branch/PR/issue content, into `03-triage.json` and `summary.md`), but does not actually call `gh`/GitHub MCP to create branches, PRs, or issues, until this is explicitly turned on later.
- Q3–Q6 remain open; revisit before Phase 4 (GitHub Action, issue filing) and before onboarding a real target repo.
- **`reference/` and `THIRD_PARTY_NOTICES.md` removed after Phase 2.** Section 0's clone-and-audit was a one-time step to decide what to seed `rules/` from; once `rules/general/` and `rules/lang/python/` were written (Phase 1) and the audit was no longer needed for anything downstream, both the cloned `reference/mavka/` and `reference/MAVKA-AUDIT.md` were deleted at the user's request, along with `THIRD_PARTY_NOTICES.md` (the MIT attribution note for the adapted rule content). No skill, script, or rule file reads from either path, so nothing downstream depends on them. Note: this leaves no attribution trail for the rule files in `rules/general/`/`rules/lang/` that originated as adaptations of MIT-licensed content from `mavka-ai/unit-tests-skills` — the MIT license technically expects the notice to travel with reused/adapted copies. Accepted as a known, deliberate tradeoff rather than an oversight.
- **Section 6.6 / 7.2 staleness-check interpretation:** `/build-context` has no `Bash` tool (Section 7.2, deliberately — "the most locked-down skill"), so it cannot run `git diff` to categorize what changed since the last build the way Section 6.6's table implies (schema files vs. docs vs. new modules vs. tests, mapped to updating one section each). Instead, it re-reads the same small set of source locations every run, regenerates candidate content for all 4 sections, and diffs each candidate against what's currently in `.qa/context.md` (with `[manual]` lines spliced back in first) to decide which sections actually changed. "More than 30% of files changed → rebuild" is approximated as "3 or 4 of the 4 sections would change → rebuild," since a file-count percentage isn't computable without git. This still satisfies the literal Phase 3 finish criteria (unchanged repo → "context is current", no rewrite; `[manual]` lines survive) without needing Bash. See `.claude/skills/build-context/SKILL.md`.
- **Section 7.1, Step 12 interpretation:** the PRD's "3 fix attempts, then delete" rule is read as applying to *mistakes in how a test was written* (wrong fixture, wrong import, wrong mock setup) — not to a mechanically correct test that asserts an expected result derived from the target's own docstring/contract or adjacent documentation, and fails because the code's actual behavior contradicts it. That second case is kept in the file, failing, and flagged distinctly (`tests_flagged_as_possible_bugs` in `01-tests.json`) rather than deleted or rewritten to match the buggy output — deleting or "fixing" it would be exactly the silent-bug-hiding failure mode Section 1 (Part 3) describes. This reading is what makes the Section 7.3 worked example possible in the first place (a previously-generated `test_apply_discount_premium_tier` is what's found failing and triaged) — a test that only ever asserts whatever the code currently returns could never surface a later regression. See `fixtures/GROUND-TRUTH.md` for how this plays out against the Phase 1 fixture's two seeded bugs.
