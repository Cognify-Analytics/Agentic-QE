---
name: generate-tests
description: Use when the user asks to generate, create, or write unit tests for code, or to increase test coverage for a file or repository.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion
context: fork
---

# Generate Tests Skill

You generate unit tests for a target file, folder, or (if no target is given) the
highest-value untested modules in the whole repo. You work on any language — detect
the stack, don't assume one.

**Target (file or folder), if given:** $ARGUMENTS

## Ground rules

- May only create or change files in the test location (Section below) and its
  test-data builders. Never touch production source code.
- Never invent a test folder — follow `rules/test-location-map.md` exactly.
- Quality over speed. Read the rules and the real dependency types before writing
  a single test. Tests that invent method names or fields are worse than no tests.
- Limits: 20 modules per run, 5 compile-fix attempts, 3 run-fix attempts per test.
  Every limit hit gets recorded, not silently ignored.

---

## Instructions

### Step 1 — Read the rules

Read every file in `rules/general/` and, once you know the language (Step 2),
every file in `rules/lang/<language>/`. If there is no `rules/lang/<language>/`
folder for the detected language, say so and continue with `rules/general/` only.

### Step 2 — Work out the stack

Look at manifest files in the target repo (`pyproject.toml`/`requirements.txt`,
`package.json`, `pom.xml`/`build.gradle`, `go.mod`, `Cargo.toml`, `*.csproj`, etc.)
to determine:
- the language
- the test framework already in use (or the conventional default for that language
  if none is configured yet)
- the command that runs the tests

If there is no test framework anywhere in the repo and none can be reasonably
assumed, say so on screen, **write `.claude-pipeline/01-tests.json` with
`"status": "failed"` and a `"reason"` explaining exactly what was missing**,
and stop. Do not silently pick one for the user. Writing the file before
stopping matters: `/test-pipeline`'s Stage 1 check (and a developer running
this skill standalone) both depend on `01-tests.json` existing to know what
happened — a stage that stops without writing anything looks identical to a
crash, and the whole point of this project's file-based handoffs (PRD
Section 6.5) is that nothing gets lost silently.

### Step 3 — Work out where tests go

Follow `rules/test-location-map.md` in order:
1. Does the repo already have tests? Use that location, even if unusual.
2. No existing tests? Use the language default from the table.
3. Can't tell? Stop and ask the user with `AskUserQuestion`. Do not guess.

### Step 4 — Read the existing inventory

If `.qa/test-inventory.json` exists, read it. It tells you what already has tests
without you having to scan the whole repo. If it does not exist, this is the first
run — you will create it at the end.

### Step 5 — Pick what to test

- If the user gave a target (`$ARGUMENTS`), use exactly that.
- Otherwise, list every source module with no corresponding test file (per the
  inventory, or by scanning if there is no inventory yet). Rank them: business
  logic and entry points first, config/constants/simple data classes last. Take
  the top 20.
- A module that is genuinely untestable in isolation (needs live network, a real
  external system, etc., with no reasonable seam to mock) is recorded as skipped
  with a `skipped_reason` — it is not silently dropped, and it is not forced.

### Step 6 — Read the dependencies

For each target, follow its imports and read the actual types it uses — parameters,
return types, injected dependencies, DTOs/entities/structs, enums, exceptions. **Do
not skip this.** It is the difference between a test that compiles and a test that
invents a method or field that does not exist.

### Step 7 — Check for existing tests for this specific target

- If a test file already exists for this target, read it fully and **add to it** —
  never create a second file for the same source module.
- If none exists, read 2–3 neighboring test files first to learn the house style
  (naming, assertion library, fixture usage) before writing anything.

### Step 8 — Check for existing test-data builders

Look for `conftest.py` fixtures, factory functions, or builder classes already in
the repo. Add to them rather than duplicating. Only put genuinely large static
fixtures (sample files, big JSON/CSV payloads) under `tests/fixtures/` — everything
else is a builder/factory, per `rules/general/cleanly-create-test-data.md`.

### Step 9 — List the test cases

For each target, list the test cases in Given-When-Then form, one per code branch
(success paths, error/validation paths, boundary conditions). Naming format:
`{method}_{state}_{outcome}`.

```
## Test Cases for OrderService.createOrder

### 1. createOrder_validRequest_returnsOrderId
- Given: a valid OrderRequest with 2 line items
- When: createOrder is called
- Then: returns a non-null order ID and saves once to the repository
- Code branch: happy path

### 2. createOrder_emptyItems_throwsValidationError
- Given: an OrderRequest with an empty items list
- When: createOrder is called
- Then: throws a validation error, repository is never called
- Code branch: validation guard
```

### Step 10 — Get approval

Ask the user to approve the test case list with `AskUserQuestion` before writing
any code.

**Skip this step entirely when running in pipeline mode.** Check
`.claude-pipeline/run.json` before Step 9's list is shown: if it exists and its
`"mode"` field is `"pipeline"`, this run was started by `/test-pipeline`, which
writes that file before invoking any stage — go straight to Step 11 without
asking. If the file doesn't exist or `"mode"` isn't `"pipeline"`, this is a
direct, standalone invocation — ask as normal.

### Step 11 — Write the test code

Write the tests at the location determined in Step 3, following the house style
learned in Step 7 and using the builders from Step 8.

### Step 12 — Verify twice

1. **Compile/build.** Up to 5 attempts to fix compile errors.
2. **Run**, and when a test fails, tell apart *why* before touching anything:
   - **A mistake in how the test itself was written** — wrong fixture, wrong
     import, wrong mock/fake setup, a typo in the assertion, a case where you
     asserted a value without checking it against the real dependency types
     from Step 6. This is on you to fix. Up to 3 fix attempts per test. If it
     still fails after 3 attempts, delete it and report it in
     `tests_removed` — it never reflects a real behavior, so there's nothing
     worth keeping.
   - **The test is mechanically correct and asserts a genuinely expected
     result — derived from the target's own docstring/contract, from adjacent
     documentation, or from an unambiguous domain fact — but the code's
     actual behavior contradicts it.** This is not a test-writing mistake, and
     no amount of retrying the test's mechanics will change a real behavioral
     gap. **Do not spend fix attempts on it, do not delete it, and do not
     weaken the assertion to match the code's current output** — that second
     move is the exact anti-pattern this whole project exists to eliminate
     (see the PRD, Section 1, Part 3). Keep the test in the file, failing,
     and record it distinctly in `01-tests.json` under
     `tests_flagged_as_possible_bugs` (not `tests_removed`) with the reason.
     Say so on screen too. This is precisely the seam `/triage-tests` (Phase 2)
     is built to pick up — a failing test here is a lead, not a defect in the
     test.
   - When genuinely unsure which of the two applies, treat it as the second
     case. Deleting or rewriting a test that might be exposing a real bug is a
     worse mistake than leaving a red test with a clear note attached.
3. **Never modify production source code to make a test pass**, in either case
   above.

### Step 13 — Get coverage

Run `scripts/parse_coverage.py` against the test run's coverage output to get a
clean per-module coverage JSON.

### Step 14 — Update the inventory and write scratch output

Update `.qa/test-inventory.json` in place (never wholesale-rewrite unless
`--rebuild` was passed) and write `.claude-pipeline/01-tests.json`.

---

## Expected output — `.qa/test-inventory.json` (committed to the repo)

```json
{
  "schema_version": 1,
  "last_updated": "2026-08-21T14:02:00Z",
  "last_updated_sha": "a1b2c3d",
  "language": "python",
  "framework": "pytest",
  "test_command": "pytest -q --cov=src --cov-report=xml",
  "test_location": "tests/",
  "coverage": { "total": 67.4, "measured_at_sha": "a1b2c3d" },
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

The `generated_by_qa` flag is load-bearing: it marks which tests this pipeline owns
and may later edit (in `/triage-tests`), and which a human wrote and must never be
touched. Get it right — set it `true` only for a test file this run created or
added generated tests into, and never flip an existing `false` to `true`.

## Expected output — `.claude-pipeline/01-tests.json` (scratch, gitignored)

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
      "reason": "could not be made to pass in 3 attempts — test-authoring mistake, not a suspected bug" }
  ],
  "tests_flagged_as_possible_bugs": [
    { "test": "calculate_discount_premiumTier_returnsDocumentedRate",
      "file": "tests/test_pricing.py",
      "reason": "expected 0.15 per docs/pricing.md; code returns 0.10. Kept failing, not deleted or rewritten — for /triage-tests to classify." }
  ],
  "notes": "Matched existing pytest fixtures in tests/conftest.py."
}
```

`tests_removed` and `tests_flagged_as_possible_bugs` are never the same test. The first is a
test this skill judged to be its own mistake and discarded. The second is a test this skill
stands behind, left in the suite, failing on purpose.

If an input this skill needs is missing and it cannot be worked out (e.g. no test
framework detectable, no manifest file at all), set `"status": "partial"` and add
a `"note"` explaining exactly what was missing. Never crash silently.

---

## Troubleshooting

**Target not found.** Report the exact path searched and ask the user to clarify
— do not guess a similarly-named file.

**No test framework detected.** Say so on screen, write the `"status": "failed"`
`01-tests.json` described in Step 2, and stop. Do not install one or assume a
default without telling the user.

**Compilation/build keeps failing after 5 attempts.** Stop, show the remaining
errors, and ask the user to resolve the underlying build issue.

**A test fails because production code's actual behavior differs from what the
test (correctly) expects.** Do not touch production code. Leave the discrepancy
noted in `01-tests.json` for `/triage-tests` to classify — this skill does not
decide whether it's a bug.

**Unsupported / unrecognized language.** Apply `rules/general/` only, tell the
user there is no `rules/lang/<language>/` yet, and proceed with extra care on
naming/location conventions.

---

## Rules reference

Always read, regardless of language:
- `rules/general/technology-stack-detection.md` — detect language/framework/test command
- `rules/general/test-case-generation-strategy.md` — INCLUDE/EXCLUDE criteria for test cases
- `rules/general/naming-conventions.md` — `{method}_{state}_{outcome}` format
- `rules/general/general-principles.md` — Given-When-Then, actual/expected, determinism, minimal mocking
- `rules/general/what-makes-good-test.md` — Clarity, Completeness, Conciseness, Resilience
- `rules/general/cleanly-create-test-data.md` — helpers and builders over inline construction
- `rules/general/keep-cause-effect-clear.md` — setup next to its assertions
- `rules/general/no-logic-in-tests.md` — no conditionals/loops/computed values in a test body
- `rules/general/keep-tests-focused.md` — one scenario per test
- `rules/general/test-behaviors-not-methods.md` — organize by observable behavior
- `rules/general/verify-relevant-arguments-only.md` — don't over-specify mock verification
- `rules/general/prefer-public-apis.md` — test through public interfaces
- `rules/general/existing-test-awareness.md` — extend, don't duplicate
- `rules/general/code-context-analysis.md` — read the full dependency graph first
- `rules/general/json-serialization.md` — no computed/derived expected payloads
- `rules/general/compilation-verification.md` — Step 12, compile/build phase
- `rules/general/test-execution-verification.md` — Step 12, run phase; fix tests, never production code

Then, for the detected language, everything under `rules/lang/<language>/` (for
example `rules/lang/python/`).

And always:
- `rules/test-location-map.md` — where tests go, per Section 6.2 of the PRD
