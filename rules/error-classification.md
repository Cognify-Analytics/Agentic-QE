---
title: Error Classification — Bad Test vs Real Bug
impact: CRITICAL
impactDescription: decides which failures get auto-fixed and which get escalated to a human; the single highest-stakes decision this project makes
tags: triage, classification, safety
---

## Error Classification — Bad Test vs Real Bug

Every test failure gets exactly one label: **SIMPLE**, **COMPLEX**, or
**AMBIGUOUS**. The label decides what happens next — see
`skills/triage-tests/SKILL.md`. This file only defines the labels.

**The rule that overrides everything else:** if the failing test is a
human-written test (`generated_by_qa: false` for its module in
`.qa/test-inventory.json`), the failure is **always COMPLEX**, no matter how
the error looks. Do not inspect the error type first and reach for SIMPLE
just because it looks like a typo. Check provenance first.

### SIMPLE — fix the test

The failure is caused by a mistake in *how the test itself was written*, not
by anything the production code actually does wrong. Fixing it never changes
what behavior is being verified — only how correctly that verification is
expressed.

| Signal | Why it's SIMPLE |
|---|---|
| Import or module-not-found error | The test references a module/path that doesn't exist or moved; the target code is untouched |
| Typo or syntax error in the test | A misspelled variable, keyword argument, or method name in the test body |
| Wrong assertion method used | e.g. comparing a float to its string form, or using an assertion that doesn't match the value's type |
| Missing or wrong fixture | The test asked for a fixture/builder that doesn't provide what it needs, or used one incorrectly |
| Obvious type mismatch in setup | Test data was constructed with the wrong type for a field, unrelated to the behavior under test |

A SIMPLE failure is only ever SIMPLE if:
1. it's in a test file this pipeline owns (`generated_by_qa: true` for that module), and
2. fixing it means editing the *test*, never the production source.

### COMPLEX — file an issue, don't touch anything

The failure indicates the production code's actual behavior is the problem,
or the test cannot be safely touched at all.

| Signal | Why it's COMPLEX | Eligible for opt-in bug-fix mode? |
|---|---|---|
| Assertion fails on business logic | The test correctly exercises a code path and gets a wrong *result*, not a wrong *expression* | Yes, but only when the expected result traces to a specific documented expectation (see below) — not merely "this looks wrong" |
| Behaviour contradicts what the docs say | `.qa/context.md`, a docstring, or adjacent documentation states one thing; the code does another | Yes — this is the clearest case, since the fix target is unambiguous |
| Timing or race condition | Passes alone, fails under load or in the full suite — a concurrency bug, not a test bug | **No** — a concurrency fix can't be safely attempted or verified blind |
| Fixing it would mean changing source code | There is no way to make this pass without touching production code | Same as whichever row above actually produced this signal |
| Failure at an integration boundary | The failure crosses into a real external dependency's behavior, not just this unit | **No** — no live external system to verify against in CI |
| The test was written by a human | Always COMPLEX regardless of anything else on this list — see the override rule above | **No** — always issue-only in v1, regardless of how strong the evidence looks |

**"Eligible for opt-in bug-fix mode" only matters when `fix_bugs` is on**
(see `skills/triage-tests/SKILL.md` Step 7.5 and PRD Section 9.1). It is
off by default; every failure in this table is issue-only, exactly as
described above, unless a run explicitly turns that mode on.

### AMBIGUOUS — always treated as COMPLEX. Never guess.

If a failure doesn't cleanly match a SIMPLE row, or you are genuinely unsure
whether the mistake is in the test or in the code, it is AMBIGUOUS. Do not
break the tie by guessing, and do not default to SIMPLE because that's the
cheaper outcome. **AMBIGUOUS is COMPLEX.** A missed opportunity to auto-fix a
test is a minor cost. A real bug auto-fixed into invisibility is the failure
this entire project exists to prevent — see PRD Section 1, Part 3.

### Applying this without `.qa/context.md`

If `.qa/context.md` doesn't exist yet (e.g. `/build-context` hasn't run),
classification still works from first principles — read the failing
assertion, the target function, and its own docstring; check for an adjacent
doc (README, `docs/*.md`) near the target module before concluding there's no
documented expectation to compare against. Note reduced confidence in the
classification reason when you had to do this without `context.md`, but do
not skip classification, and do not treat "no context file" as a reason to
default to SIMPLE.
