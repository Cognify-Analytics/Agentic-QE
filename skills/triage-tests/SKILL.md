---
name: triage-tests
description: Use when the user asks to run tests and triage, classify, or fix failures, or to file issues for failing tests.
allowed-tools: Read, Edit, Glob, Grep, Bash
context: fork
---

# Triage Tests Skill

You run the test suite, classify every failure as SIMPLE (a bad test) or
COMPLEX (a suspected real bug), fix only what is safe to fix, and hand
everything else to a named person. You never guess, and you never let a real
bug disappear behind a quietly "fixed" test.

**Arguments, if given:** $ARGUMENTS — pass `--live` to actually create
branches/PRs/issues on GitHub (see Step 7/8). Without it, this run is
**report-only**: every classification, fix, and planned issue/PR is computed
and written out in full, but nothing is actually pushed or filed. Report-only
is the default because this project is still early in its build — treat
`--live` as something the user opts into, not the default you assume.

When invoked by `/test-pipeline` rather than directly, mode comes from
`.claude-pipeline/run.json`'s `"live"` field instead of `$ARGUMENTS` (the
orchestrator writes that file before invoking any stage, and forwards
`--live` in its own invocation too — check either, they must agree; if
they don't, trust `run.json` and note the mismatch in `03-triage.json`).

## The one rule that matters most

**A real bug labelled SIMPLE and quietly fixed is the failure this whole
project exists to prevent.** Every other rule below exists in service of
that one. When in doubt, escalate — never guess your way to SIMPLE.

## Ground rules (Section 9 of the PRD — non-negotiable, live or report-only)

1. Never change production source code. A fix that would require a source
   change is automatically COMPLEX.
2. Never edit a test that is not `generated_by_qa: true` for its module in
   `.qa/test-inventory.json`. A human-written test that fails goes straight
   to COMPLEX, no matter what the failure looks like.
3. Never push to a main/default branch. Fixes go to a branch, then a PR —
   and only in `--live` mode.
4. Never merge anything, ever, in any mode.
5. A suspected bug gets an issue, never a `// might be a bug` comment left
   in the code or the test.
6. Every limit hit (2 fix attempts, 10 issues, 30 turns) is a hard stop and
   gets recorded in `caps_hit`, not silently absorbed.

---

## Instructions

### Step 1 — Read the context

Read `.qa/context.md` if it exists. You cannot judge whether a failure is a
bug unless you know what the code is supposed to do. If it's missing, warn
on screen and continue with less confidence (see
`${CLAUDE_PLUGIN_ROOT}/rules/error-classification.md`'s "Applying this without context.md"
section) — do not stop. If `context_sha` in the file differs from the
current git SHA (or, if this repo has no git history yet, from
`.qa/test-inventory.json`'s `last_updated_sha`), warn that the context may be
stale and carry on with less confidence.

### Step 2 — Get the test command

Read `test_command` from `.qa/test-inventory.json`. If that file is missing,
fall back to `.claude-pipeline/01-tests.json`. **Do not guess the test
command** — if neither file has it, stop and ask the user.

### Step 3 — Run the tests

Run the test command. Save the full raw output to
`.claude-pipeline/raw-test-output.txt`.

### Step 4 — Extract every failure

For each failing test, pull out: test name, file, error type, message, and
stack trace/traceback.

### Step 5 — Read the rules and classify

Read `${CLAUDE_PLUGIN_ROOT}/rules/error-classification.md`. For each failure:

1. **Check provenance first.** Look up the failure's test file in
   `.qa/test-inventory.json`'s `modules`. If the module's `generated_by_qa`
   is `false`, the classification is **COMPLEX**, full stop — do not go on
   to inspect the error type. (If the inventory doesn't cover this file at
   all, treat it the same as `generated_by_qa: false` — you have no basis
   to believe this pipeline owns it.)
2. Otherwise, match the failure against the SIMPLE/COMPLEX tables in
   `${CLAUDE_PLUGIN_ROOT}/rules/error-classification.md`.
3. If it doesn't cleanly match, it's AMBIGUOUS — which is COMPLEX. Never
   guess.

Record every classification with a one-line, specific reason (not "looks
wrong" — cite the assertion, the docstring, the doc line, or the exact
provenance check that decided it).

### Step 6 — SIMPLE: fix the test

For each SIMPLE failure:

1. Create a branch `auto-fix/triage-<sha>` if one doesn't already exist for
   this run (all SIMPLE fixes in a run share one branch).
2. Make the smallest possible fix **to the test file** — never to production
   source. This is fixing a mistake in how the test was written (a typo,
   a wrong import, a wrong fixture keyword), not re-deriving what the test
   should assert.
3. Re-run just that test.
4. If it passes: keep the fix.
5. If it still fails: undo the change, relabel the failure COMPLEX, and move
   on. Maximum **2 attempts** per failure before relabeling.

If, partway through, you realize the "fix" would require touching production
code to make the test pass — stop immediately, undo any partial edit, and
relabel COMPLEX. Do not rationalize a source change as a test fix.

### Step 7 — COMPLEX/AMBIGUOUS: find the owner and check for an existing issue

1. Run `${CLAUDE_PLUGIN_ROOT}/scripts/resolve_owners.py <path>` for the failing file's source
   module. It returns `owners: []` if there's no CODEOWNERS or no match —
   that's a normal outcome, not an error; file the issue without an
   assignee rather than guessing one.
2. **Look for an existing open issue first**, GitHub MCP server if
   available, otherwise the `gh` CLI (`gh issue list --search ...`). If one
   clearly matches this failure, comment on it instead of opening a new one.
3. Otherwise, draft a new issue from `${CLAUDE_PLUGIN_ROOT}/templates/github-issue-template.md`,
   filling in the failure output, the relevant excerpt of `.qa/context.md`
   (or whatever you used in its absence, per Step 1), and the resolved
   owner if any.
4. **Report-only mode (default):** do not actually call the GitHub MCP
   server or `gh` — write the fully-drafted issue/comment content into
   `03-triage.json`'s `issues_created`/`issues_commented` and show it on
   screen, clearly marked `[REPORT-ONLY — not filed]`.
5. **`--live` mode:** actually create the issue (GitHub MCP server first; if
   it's not configured/available, fall back to `gh issue create` /
   `gh issue comment`) and record the real URL.

**Cap: 10 issues per run.** Beyond that, stop opening individual issues and
combine everything past the cap into one summary issue. Record this in
`caps_hit`.

### Step 8 — Open the PR for any fixes made

If Step 6 produced any commits on the `auto-fix/triage-<sha>` branch:
- **Report-only mode:** note in `03-triage.json` and on screen what PR
  *would* be opened (branch, files changed, one-line summary per fix),
  marked `[REPORT-ONLY — not opened]`. Do not push the branch.
- **`--live` mode:** push the branch and open a PR (GitHub MCP first, `gh
  pr create` as fallback). Never merge it.

### Step 9 — Write the result

Write `.claude-pipeline/03-triage.json` (schema below). This is scratch —
gitignored, not committed.

---

## Expected output — `.claude-pipeline/03-triage.json`

```json
{
  "status": "ok",
  "mode": "report-only",
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
      "reason": "Premium tier discount returns 10%, docs/pricing.md says 15%. Looks like a real bug in src/pricing.py." }
  ],
  "fixes_applied": [
    { "test": "test_create_order_valid",
      "change": "corrected import path to src.models.order",
      "attempts": 1 }
  ],
  "pr_url": null,
  "pr_planned": {
    "branch": "auto-fix/triage-a1b2c3d",
    "files_changed": ["tests/test_orders.py"],
    "summary": "1 test import fix"
  },
  "issues_created": [
    { "url": null,
      "test": "test_apply_discount_premium_tier",
      "owners": ["@payments-team"],
      "reason": "suspected real bug in discount calculation",
      "report_only": true,
      "drafted_body": "... full issue body from the template ..." }
  ],
  "issues_commented": [],
  "escalated": [],
  "caps_hit": []
}
```

`mode` is always `"report-only"` or `"live"`. When `"report-only"`,
`pr_url` and every issue's `url` are `null`, and each carries
`"report_only": true` with the drafted content still fully present — a
human reading this file must be able to see exactly what would have
happened.

---

## Troubleshooting

**`.qa/context.md` missing.** Warn, continue with reduced confidence — see
`${CLAUDE_PLUGIN_ROOT}/rules/error-classification.md`. Do not stop.

**`.qa/test-inventory.json` missing (so you can't check `generated_by_qa`).**
Treat every failing test as if it were human-written (COMPLEX-only) until
proven otherwise — the safe default when provenance is unknown. Say so in
the run's notes.

**Test command unknown and can't be found anywhere.** Stop and ask the user.

**GitHub MCP server not configured/available.** Fall back to the `gh` CLI.
If `gh` isn't authenticated either, report-only mode still works fully
(nothing needs to actually reach GitHub); in `--live` mode, stop and tell the
user GitHub access isn't available rather than silently staying in
report-only.

**More than 10 COMPLEX/AMBIGUOUS failures.** File the first 10 individually,
then one combined summary issue for the rest, and record the cap in
`caps_hit`.

**A SIMPLE fix's second attempt also fails.** Undo it, relabel COMPLEX,
move on — don't try a third time.

---

## Rules reference

- `${CLAUDE_PLUGIN_ROOT}/rules/error-classification.md` — SIMPLE / COMPLEX / AMBIGUOUS, and the
  human-written-test override
- `${CLAUDE_PLUGIN_ROOT}/templates/github-issue-template.md` — issue body shape
- `${CLAUDE_PLUGIN_ROOT}/scripts/resolve_owners.py` — file path → CODEOWNERS owner (or none)
