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

Also pass `--fix-bugs` to turn on the opt-in bug-fix mode (Step 7.5/8.5) —
off by default, unrelated to `--live` (it works in either mode: report-only
`--fix-bugs` computes and shows what it *would* fix without touching any
file; `--live --fix-bugs` actually applies it). See Ground rule 1 below and
PRD Section 9.1 before turning this on.

Pass `--clickup-branches` for a repo whose branch policy requires a ClickUp
task ID in every branch name — see "Branch names" below.

When invoked by `/test-pipeline` rather than directly, mode comes from
`.claude-pipeline/run.json`'s `"live"` and `"fix_bugs"` fields instead of
`$ARGUMENTS` (the orchestrator writes that file before invoking any stage,
and forwards `--live`/`--fix-bugs` in its own invocation too — check
either, they must agree; if they don't, trust `run.json` and note the
mismatch in `03-triage.json`). A missing `"fix_bugs"` field means off —
never infer it as on.

## The one rule that matters most

**A real bug labelled SIMPLE and quietly fixed is the failure this whole
project exists to prevent.** Every other rule below exists in service of
that one. When in doubt, escalate — never guess your way to SIMPLE.

## Ground rules (Section 9 of the PRD — non-negotiable, live or report-only)

1. Never change production source code. A fix that would require a source
   change is automatically COMPLEX. **The one narrow, explicit exception:**
   when `fix_bugs` is on (see Step 7.5), a bounded, capped, verified fix may
   be attempted for a small subset of COMPLEX failures — never silently,
   never by default, and never without the issue from Step 7 already
   existing first. Everyone who doesn't turn `fix_bugs` on gets exactly the
   original rule with no exception.
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

### Step 0 — Local `--live` runs: confirm GitHub access

**Skip this step in report-only mode and in CI mode** (`run.json`'s
`"mode"` is `"ci"` — the workflow already supplies `GH_TOKEN`, `GH_REPO`
and `ci.pr_base_branch`).

For a local `--live` run, you need the same three things CI gets for free:
which repo to file against, which remote to push to, and which branch a PR
should target. If `.claude-pipeline/run.json` has a `"local"` object,
`/test-pipeline` already established them — use it. Otherwise (you were
invoked directly), run `python ${CLAUDE_PLUGIN_ROOT}/scripts/gh_preflight.py`
yourself and use its output the same way. If it reports `"ok": false`,
stop before running any test, show the user every entry in `problems`, and
tell them they can fix those or re-run without `--live`. Do not silently
fall back to report-only.

Everywhere below that says "the local repo/remote/base/start branch", it
means these values: `repo`, `remote`, `pr_base_branch`, `start_branch`.
Pass `--repo <repo>` on every `gh issue`/`gh pr` command in a local live
run, so `gh` never has to guess between several remotes, and push only to
`<remote>`.

### Branch names — never make one up

Every branch this skill creates is named by
`${CLAUDE_PLUGIN_ROOT}/scripts/branch_names.py`, so CI, local runs and the
workflow's own `.qa/` branch all follow one rule. Read the names from
`run.json`'s `branch_naming` object (the CI workflow and `/test-pipeline`
both write it). If it's missing — you were invoked directly — run
`python ${CLAUDE_PLUGIN_ROOT}/scripts/branch_names.py --branch <current branch> --sha <short sha>`
yourself, adding `--clickup` if `--clickup-branches` was passed, and use
its output the same way.

- `branches.triage` — the one branch for this run's SIMPLE fixes (Step 6).
- `branches.bugfix` — a template for each bug fix (Step 7.5): replace
  `{issue_number}` with the issue's number.

With ClickUp naming on, these carry the task ID of the branch the run
started from — `bug/CU-101010-cache-loading` gives
`auto-fix/CU-101010-triage-<sha>` and `auto-fix/CU-101010-bugfix-issue-9`.
Use them exactly as given; never shorten, re-case or reword them.

**If `branch_naming.clickup` is true and `branches` is null**, no task ID
could be found, and any branch pushed would break the repo's naming policy.
Then **push no branch at all**: run Steps 6 through 8.5 as if in
report-only mode — Step 6 fixes and verifies in the working tree without
creating a branch, and nothing is committed, pushed or opened as a PR —
even in `--live` mode. Step 7's issues are still filed in `--live` mode;
they need no branch. Copy `branch_naming.problem` into `03-triage.json`'s
`branch_naming_problem` and say it on screen, so nobody wonders why a live
run opened no PR.

### Step 1 — Read the context

Read `.qa/context.md` if it exists. You cannot judge whether a failure is a
bug unless you know what the code is supposed to do. If it's missing, warn
on screen and continue with less confidence (see
`${CLAUDE_PLUGIN_ROOT}/rules/error-classification.md`'s "Applying this without context.md"
section) — do not stop. If `context_sha` in the file differs from the
current git SHA (or, if this repo has no git history yet, from
`.qa/test-inventory.json`'s `last_updated_sha`), warn that the context may be
stale and carry on with less confidence.

### Step 2 — Get the test command(s)

Read `.qa/test-inventory.json`. **Check for a `stacks` object first** — if
present, this is a multi-stack repo (see `/generate-tests`' multi-stack
variant of this file): read every stack's `test_command` under
`stacks.<name>.test_command`, there is no single top-level `test_command`
to read in this shape. If `stacks` is absent, read the single top-level
`test_command` as before.

If `.qa/test-inventory.json` is missing entirely, fall back to
`.claude-pipeline/01-tests.json` (same `stacks`-or-flat check applies
there too). **Do not guess the test command** — if neither file has it (for
any stack, in a multi-stack repo): **in CI mode**
(`.claude-pipeline/run.json` exists with `"mode"` `"ci"`), write
`.claude-pipeline/03-triage.json` with `"status": "failed"` and a
`"reason"` explaining the test command couldn't be found, and stop.
**Interactively**, stop and ask the user.

**Run every stack, always.** Even if this CI run's `ci.targets` only
touched one stack (that only matters to `/generate-tests`), run *every*
stack's full suite here — a bug in a stack the PR didn't touch is still a
bug, and skipping it would silently shrink triage's coverage every run.

### Step 3 — Run the tests

**Redirect the output to a file; never let the full run stream into your
context.** A passing suite's output can run to thousands of lines, and
every one of them would be tokens spent to learn "nothing failed."

Run the test command with its output redirected to
`.claude-pipeline/raw-test-output.txt` and capture the exit code, e.g.
`<test command> > .claude-pipeline/raw-test-output.txt 2>&1; echo "exit=$?"`.
Then read **only the tail** (the last ~15 lines) to get the totals line.

**Multi-stack:** run each stack's test command separately (in that stack's
own subtree/environment — they are typically incompatible runtimes), and
save each stack's raw output to its own
`.claude-pipeline/raw-test-output-<stack>.txt` (e.g.
`raw-test-output-backend.txt`, `raw-test-output-frontend.txt`) instead of
one combined file — two frameworks' output interleaved in one file is not
reliably parseable. Capture one exit code per stack.

**A stack that failed before any test ran is a tooling problem, not a
test failure.** Recognise it from the tail: no test results at all, plus
an error from the tooling itself, for example
- `Cannot find dependency '@vitest/coverage-v8'`
- `Test environment jest-environment-jsdom cannot be found`
- `Preset ts-jest not found`
- `ModuleNotFoundError: No module named 'pytest_cov'` / `unrecognized arguments: --cov`
- `No tests found` / `Tests run: 0` caused by configuration
- a Maven/Gradle build failure outside test sources

Then:
1. **If the error is about coverage only**, re-run the same command once
   with its coverage flags removed (`--coverage…`, `--cov…`, the JaCoCo
   goals or init script). If that runs, triage its results normally;
   triage only needs pass/fail, not coverage.
2. Record the gap in `03-triage.json`'s `tooling_gaps`. Also add it to
   `.qa/test-inventory.json`'s `tooling_gaps` (same entry shape as
   `/generate-tests` writes, `"detected_by": "triage-tests"`), replacing
   only your own earlier entries for this stack. That's how it reaches
   section 5 of `.qa/context.md`, where the developer is told what to
   install.
3. If the stack still couldn't run, classify nothing and file no issues
   for it. A missing package is not a code bug. Put one line in
   `escalated` naming the stack and the missing tool, and carry on with
   the other stacks.

**If every stack exited 0 (a green suite): stop here.** There are no
failures to classify, so Steps 4 through 8.5 have nothing to act on. Record
the totals from the tail you already read, skip to Step 9, and write
`03-triage.json` with empty `classifications`/`fixes_applied`/
`issues_created`. Do **not** read the raw output file — it is kept on disk
for the CI artifact (so a disputed run is still arguable after the fact),
not for you to load. In a CI run, `.qa/` may still have changes to commit,
so Step 8 still applies even on a green suite; go there, then Step 9.

### Step 4 — Extract every failure

*(Only reached when at least one stack failed — see Step 3.)*

**Pull out failures with targeted searches, not by reading the whole
file.** Grep the raw output for the framework's failure markers to get the
list, then read only the surrounding block for each one — reading a
5,000-line log to find 3 failures costs far more than 3 targeted reads.

| Framework | Failure markers to grep |
|---|---|
| pytest | `FAILED `, `ERROR ` (short summary at the end) |
| Jest | `● ` (one block per failing test: `● describe › test name`), `FAIL ` (per file) |
| Vitest | `FAIL `, `×` / `✗`, `AssertionError` |
| node:test | `not ok `, `✖` |
| Maven Surefire | `<<< FAILURE!`, `<<< ERROR!`, and the `[ERROR] Failures:` / `[ERROR] Errors:` summary |
| Gradle | `> … FAILED` lines (`OrderServiceTest > createOrder_validRequest_returnsOrderId() FAILED`) |
| Go | `--- FAIL:` |

**JVM builds also write structured results**, which are more reliable than
the console: `target/surefire-reports/*.txt` / `TEST-*.xml` (Maven) and
`build/test-results/test/TEST-*.xml` (Gradle), one file per test class,
with the full assertion message and stack trace of each failure. Grep
those for `<failure`/`<error` and read only the failing class's file. A
**compile error** in a test source (`COMPILATION ERROR`, `Compilation
failed`, `e: file://…`) means no test ran at all in that module: record
it as one failure against the test file that failed to compile, and
classify it like any other.

For each failing test, pull out: test name, file, error type, message, and
stack trace/traceback. **Multi-stack:** also record which stack each
failure came from (the file path's stack, per Step 2) — Step 9's output
schema carries a `"stack"` field per failure for exactly this.

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

1. Create the branch named `branches.triage` (see "Branch names") if it
   doesn't already exist for this run — all SIMPLE fixes in a run share
   one branch.
2. Make the smallest possible fix **to the test file** — never to production
   source. This is fixing a mistake in how the test was written (a typo,
   a wrong import, a wrong fixture keyword), not re-deriving what the test
   should assert.
3. Re-run just that test, with the single-test command for its framework
   (`${CLAUDE_PLUGIN_ROOT}/rules/general/test-execution-verification.md`
   lists them — `npx vitest run <file>`, `./mvnw -q test -Dtest=<Class>#<method> -Dsurefire.failIfNoSpecifiedTests=false`,
   `./gradlew test --tests '<fqcn>.<method>'`, …). Never a watch mode.
4. If it passes: keep the fix.
5. If it still fails: undo the change, relabel the failure COMPLEX, and move
   on. Maximum **2 attempts** per failure before relabeling.

If, partway through, you realize the "fix" would require touching production
code to make the test pass — stop immediately, undo any partial edit, and
relabel COMPLEX. Do not rationalize a source change as a test fix.

### Step 7 — COMPLEX/AMBIGUOUS: find the owner and check for an existing issue

1. Run `${CLAUDE_PLUGIN_ROOT}/scripts/resolve_owners.py <path>` for the failing file's source
   module — in `--live` mode with `--github-repo <repo>` added (`$GH_REPO`
   in CI, the local repo from Step 0 locally), so it also reports who
   GitHub will actually accept as an assignee (see "Assigning CODEOWNERS"
   below). In report-only mode leave the flag off: it calls GitHub, and
   report-only never does. `owners: []` means no CODEOWNERS or no match —
   a normal outcome, not an error; file the issue without an assignee
   rather than guessing one.
2. **Build a stable fingerprint for this failure**: `{test name} ({file})` —
   e.g. `calculate_discount_premiumTier_returnsDocumentedRate
   (tests/test_pricing.py)`. Put it verbatim in the issue title (prefixed by
   the template's own title convention, if any). This is what makes a
   re-run idempotent — a run's issue for the same failure must always
   produce the same title.
3. **Look for an existing open issue first**, GitHub MCP server if
   available, otherwise the `gh` CLI (`gh issue list --search ...`) —
   search on the fingerprint from step 2, not just free-text keywords. If
   one clearly matches this failure, comment on it instead of opening a new
   one — this is what keeps a re-triggered run (e.g. `workflow_dispatch` on
   the same PR) from filing a duplicate every time.
4. Otherwise, draft a new issue from `${CLAUDE_PLUGIN_ROOT}/templates/github-issue-template.md`,
   filling in the fingerprinted title, the failure output, the relevant
   excerpt of `.qa/context.md` (or whatever you used in its absence, per
   Step 1), and the resolved owners if any.
5. **Report-only mode (default):** do not actually call the GitHub MCP
   server or `gh` — write the fully-drafted issue/comment content into
   `03-triage.json`'s `issues_created`/`issues_commented` and show it on
   screen, clearly marked `[REPORT-ONLY — not filed]`.
6. **`--live` mode:** actually create the issue (GitHub MCP server first; if
   it's not configured/available, fall back to `gh issue create` /
   `gh issue comment` — with `--repo` set to the local repo when running
   locally, per Step 0) and record the real URL. Then assign it to the
   code owners, per "Assigning CODEOWNERS" below. When you commented on an
   existing issue instead, add any of this run's assignees it doesn't
   already have — an issue nobody is assigned to is the one that sits.

**Cap: 10 issues per run.** Beyond that, stop opening individual issues and
combine everything past the cap into one summary issue. Record this in
`caps_hit`.

#### Assigning CODEOWNERS (issues and PRs, local and CI alike)

Every issue and PR this skill opens goes to the people CODEOWNERS names for
the code involved — the same rule in CI and locally, since both have `gh`.
Use the `resolve_owners.py --github-repo` output; never add an owner it
didn't return.

- **Issues:** assign every login in `assignees`
  (`gh issue edit <n> --repo <repo> --add-assignee a,b`).
- **PRs:** assign `assignees` and request review from `reviewers`
  (`gh pr edit <n> --repo <repo> --add-assignee a,b --add-reviewer c,org/team`).
  GitHub also requests review from the code owners of the *changed* files
  on its own; requesting `reviewers` explicitly matters because a test-fix
  PR's changed files are tests, whose owners are often not the owners of
  the code under test.
- **`mention_only`** owners (emails, people without repo access, teams
  whose members couldn't be listed) can't be assigned. Name them on the
  issue/PR body's owners line instead so they are still notified.

**Assign in a separate call after creating, never in the create call.** An
assignee or reviewer GitHub rejects can fail `gh issue create`/`gh pr create`
outright, and a lost issue is far worse than an unassigned one. If the
follow-up call fails, keep the issue/PR, record the error in that entry's
`assignment_error` in `03-triage.json`, and move on — never retry by
dropping owners one at a time.

In report-only mode, record `owners` as the would-be assignees and do not
call GitHub to check them.

### Step 7.5 — Attempt a bug fix (opt-in: `fix_bugs`, off by default)

**Skip this step entirely unless `fix_bugs` is on** (per the Arguments
section above). This is the one narrow exception to Ground rule 1, and it
must never activate silently — if you're not certain it's on, treat it as
off.

Run this once per COMPLEX failure, right after Step 7 has filed (or
found/commented on) its issue. **Never attempt a fix for a failure that
doesn't have an issue yet** — the issue is the paper trail this whole
feature depends on, and Step 7.5 must never run ahead of it.

**Check eligibility first — all of these must hold:**
1. The failure's classification reason (Step 5) matches one of the two
   "Yes" rows in `${CLAUDE_PLUGIN_ROOT}/rules/error-classification.md`'s
   "Eligible for opt-in bug-fix mode?" column — i.e. there is a specific
   documented expectation (a `.qa/context.md` line, a docstring, or
   adjacent docs) that the code contradicts. A vague "this looks wrong"
   is not enough.
2. It is **not** a timing/race condition, **not** an integration-boundary
   failure, **not** from a human-written test, and **not** AMBIGUOUS. All
   four are always issue-only in v1, `fix_bugs` or not — see the table.
3. This run hasn't hit the bug-fix cap yet (**3 per run** — separate from
   Step 7's 10-issue cap).

Any failure that fails even one of these checks gets an issue only,
exactly as Step 7 already did — do not attempt a fix, and do not record a
reason why in `bug_fix_prs_created` (that array is only for attempts, not
every failure considered).

**If eligible, attempt the fix:**
1. Create the branch named by `branches.bugfix`, with this issue's number
   filled in (see "Branch names"), off the same base Step 8 will use, if
   one doesn't already exist for this issue.
2. Make the smallest possible change to production source that makes the
   documented/expected behavior true — scoped to the file(s) the failure's
   stack trace directly implicates. **Never edit the failing test itself
   in this step** — that would silently do what Ground rule 1 exists to
   prevent (rewrite the check instead of the code). If the smallest safe
   fix would touch more than **2 files**, or any file the stack trace
   doesn't point to, stop and abandon it — this is too large to attempt
   blind. Record the abandonment in `escalated`, not `caps_hit` (it isn't
   a limit, it's a scope judgment).
3. Verify twice: re-run the specific failing test, then the **whole**
   stack's suite (not just this test) — a change that fixes one test
   while breaking three others is not a safe fix. Maximum **2 attempts**.
   If it still isn't clean after 2, undo every change on the branch,
   leave the issue as issue-only, and record the abandoned attempt (with
   why) in `03-triage.json`'s `escalated`.
4. **Report-only mode:** do not touch any file on disk. Write what the fix
   *would* change — file(s), a one-line summary of the change, and what
   verification would need to show — into `03-triage.json`'s
   `bug_fix_prs_created`, marked `"report_only": true`, `"pr_url": null`.
5. **`--live` mode:** commit the verified fix to the branch (nothing else
   — keep it isolated from any SIMPLE-fix or `.qa/` commits) and push
   (to the local remote from Step 0, when running locally). Do
   not open the PR yet — that's Step 8.5, so both PR and issue-comment
   links land together.

**Cap: 3 bug-fix attempts per run.** Once hit, every remaining eligible
failure stays issue-only (already filed in Step 7) — do not attempt a 4th.
Record the cap in `caps_hit`.

### Step 8 — Open the PR for any fixes made

**Pick the base branch first.** In CI mode (`.claude-pipeline/run.json`
exists with `"mode"` `"ci"`), the PR must be based on `run.json`'s
`ci.pr_base_branch` — this is the developer's own PR head branch, so the fix
flows back into their PR rather than being stranded against the repo's
default branch. **If `ci.pr_base_branch` is missing, do not guess a base —
fall back to report-only for this step** (note what would have been opened,
same as below, and record why in `03-triage.json`). Locally, base it on the
local base branch from Step 0 — never on whatever branch happens to be
checked out by now, since Step 6 has moved you onto the auto-fix branch.
In report-only mode, where Step 0 was skipped, note the current branch as
the would-be base.

**This step commits test fixes only. Never commit `.qa/` here.** That
folder is recorded separately — by the CI workflow's own "Record the run in
`.qa/`" step, which runs after every stage has finished, and by the
developer's own commit when running locally. The reason is a timing one:
`.qa/runs/<date>-<sha>.json` is written by `/test-pipeline`'s Finish
section, which runs *after* this stage, so it does not exist yet at this
point in the run. Committing `.qa/` from here would silently miss the run
record every time, and would now also duplicate what the workflow commits.

If Step 6 produced any commits on the `branches.triage` branch:
- **Report-only mode:** note in `03-triage.json` and on screen what PR
  *would* be opened (branch, files changed, one-line summary per fix),
  marked `[REPORT-ONLY — not opened]`. Do not push the branch.
- **`--live` mode:** create the branch if it doesn't already exist, commit
  the SIMPLE fixes onto it, push (to the local remote from Step 0, when
  running locally), and open a PR against the base branch
  chosen above (GitHub MCP first, `gh pr create` as fallback). Never merge
  it. Then assign it per "Assigning CODEOWNERS" in Step 7: run
  `resolve_owners.py --github-repo <repo>` over the **source modules** the
  fixed tests cover (one call, every path), not the test files.

If Step 6 produced no fixes, there is nothing to open a PR for — say so and
move on. An empty run is a normal outcome, not a failure.

### Step 8.5 — Open the PR for any bug fixes, and link it to the issue

**Skip entirely unless `fix_bugs` is on and Step 7.5 produced at least one
verified fix this run.** This PR is always separate from Step 8's — a
production-code change and a test typo fix carry different review burdens,
and a reviewer must be able to accept one without the other.

For each fix Step 7.5 verified (its `branches.bugfix` branch already has
the commit in `--live` mode):

- **Report-only mode:** note in `03-triage.json` and on screen what PR
  *would* be opened (branch, file(s) changed, the issue it relates to, the
  verification results), marked `[REPORT-ONLY — not opened]`.
- **`--live` mode:** push the branch if not already pushed, and open a PR
  against the same base as Step 8 (GitHub MCP first, `gh pr create` as
  fallback), using
  `${CLAUDE_PLUGIN_ROOT}/templates/bug-fix-pr-template.md` for the body.
  The template's own warning banner and "Relates to #N" (never
  "Fixes"/"Closes") are load-bearing — do not paraphrase them away. Record
  the real PR URL, then assign it per "Assigning CODEOWNERS" in Step 7,
  using the owners of the source file(s) the fix changed. **Never merge it** — same Rule 4 as every other PR this
  skill opens.
- **Either mode:** comment on the issue Step 7 filed, linking back to this
  PR (the real URL in `--live` mode, the report-only equivalent
  otherwise) — the issue and the PR must reference each other in both
  directions, not just PR → issue.

### Step 8.9 — Local `--live` runs: put the developer back

**Skip in CI** (the runner is thrown away), **in report-only mode**, and
when "Branch names" blocked every branch (nothing was committed, so there
is nothing to step away from).

Steps 6 and 7.5 checked out the pipeline's own fix branches. On a CI runner that
doesn't matter; on a developer's machine it would leave them on a bot
branch. Once every push and PR above is done, run
`git checkout <start_branch>` (from Step 0). Uncommitted work — `.qa/`, and
any generated tests that were not committed to an auto-fix branch — comes
back with you, as it went. A test file that *was* committed to the
auto-fix branch stays there and leaves this working tree; that is
intended, since it reaches `start_branch` when the developer merges the
PR. Say so on screen and name the PR, so a missing file is never a surprise.

If the checkout fails (a conflict with uncommitted changes), do not force
it and do not stash anything. Tell the user which branch they are on, why
the switch failed, and the exact command to get back.

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
    "summary": "1 test import fix",
    "owners": ["@orders-dev"],
    "assignees": null,
    "reviewers": null,
    "assignment_error": null
  },
  "issues_created": [
    { "url": null,
      "test": "test_apply_discount_premium_tier",
      "owners": ["@alice", "@acme/payments"],
      "assignees": null,
      "mention_only": null,
      "assignment_error": null,
      "reason": "suspected real bug in discount calculation",
      "report_only": true,
      "drafted_body": "... full issue body from the template ..." }
  ],
  "issues_commented": [],
  "bug_fix_prs_created": [],
  "branch_naming_problem": null,
  "tooling_gaps": [],
  "escalated": [],
  "caps_hit": []
}
```

`tooling_gaps` uses the same entry shape as `/generate-tests`' inventory
field (`stack`, `tool`, `needed_for`, `version`, `evidence`, `effect`,
`detected_by`, `detected_at_sha`). It is `[]` when every stack started
normally (see Step 3).

`mode` is always `"report-only"` or `"live"`. When `"report-only"`,
`pr_url` and every issue's `url` are `null`, and each carries
`"report_only": true` with the drafted content still fully present — a
human reading this file must be able to see exactly what would have
happened.

`owners` is always the raw CODEOWNERS result. `assignees`/`reviewers`/
`mention_only` are what `resolve_owners.py --github-repo` returned and
were applied — `null` in report-only mode, where GitHub is never asked
(the drafted body still names `owners`). `assignment_error` is the
follow-up assign call's error if it failed, otherwise `null`.

`branch_naming_problem` is `null` unless ClickUp branch naming blocked every
branch this run (see "Branch names") — then it holds the reason, and
`pr_url` and every bug-fix `pr_url` are `null` even in `"live"` mode.

`bug_fix_prs_created` is always `[]` unless `fix_bugs` was on for this run
(see Step 7.5/8.5). Each entry:

```json
{
  "pr_url": null,
  "issue_url": null,
  "test": "test_apply_discount_premium_tier",
  "file_changed": "src/pricing.py",
  "summary": "Changed premium tier discount rate from 0.10 to 0.15 to match docs/pricing.md",
  "tests_rerun": { "target_test": "passed", "full_suite": "passed" },
  "owners": ["@alice", "@acme/payments"],
  "assignees": null,
  "reviewers": null,
  "assignment_error": null,
  "report_only": true
}
```

`report_only`/`pr_url`/`issue_url` follow the same convention as
`issues_created` above. An eligible failure that was attempted but
abandoned (scope too large, or still failing after 2 attempts) does **not**
get an entry here — it goes in `escalated` instead, with the reason.

**Multi-stack variant:** `totals` stays the sum across every stack; add a
`totals_by_stack` object alongside it, keyed by stack name, each value the
same `{tests, passed, failed}` shape. Every entry in `classifications`,
`fixes_applied`, `issues_created`, `issues_commented`, and
`bug_fix_prs_created` carries a `"stack"` field naming which stack it came
from, e.g.
`{ "test": "test_require_user_access...", "file": "backend/tests/test_auth.py", "stack": "backend", "type": "COMPLEX", "reason": "..." }`.
Nothing else in the schema changes.

---

## Troubleshooting

**`.qa/context.md` missing.** Warn, continue with reduced confidence — see
`${CLAUDE_PLUGIN_ROOT}/rules/error-classification.md`. Do not stop.

**`.qa/test-inventory.json` missing (so you can't check `generated_by_qa`).**
Treat every failing test as if it were human-written (COMPLEX-only) until
proven otherwise — the safe default when provenance is unknown. Say so in
the run's notes.

**Test command unknown and can't be found anywhere.** In CI mode, write
`03-triage.json` with `"status": "failed"` and stop — do not ask.
Interactively, stop and ask the user.

**GitHub MCP server not configured/available.** Fall back to the `gh` CLI.
If `gh` isn't authenticated either, report-only mode still works fully
(nothing needs to actually reach GitHub); in `--live` mode, stop and tell the
user GitHub access isn't available rather than silently staying in
report-only. Locally, Step 0's preflight should already have caught this
before any test ran.

**Local preflight refuses because the branch isn't pushed.** This is on
purpose. CI always targets a branch that exists on GitHub; locally, an
auto-fix branch cut from unpushed commits would carry them into the PR.
The developer pushes first (`git push -u <remote> <branch>`), or runs
report-only.

**More than 10 COMPLEX/AMBIGUOUS failures.** File the first 10 individually,
then one combined summary issue for the rest, and record the cap in
`caps_hit`.

**A SIMPLE fix's second attempt also fails.** Undo it, relabel COMPLEX,
move on — don't try a third time.

**A bug fix's second attempt still fails, or the fix would touch more than
2 files.** Undo every change on that branch, leave the failure issue-only
(the issue from Step 7 stays as-is), and record the abandoned attempt in
`escalated`. Never fall back to a partial or unverified fix.

**More than 3 eligible bug fixes in one run.** Attempt the first 3, leave
the rest issue-only, and record the cap in `caps_hit` — same pattern as the
10-issue cap.

---

## Rules reference

- `${CLAUDE_PLUGIN_ROOT}/rules/error-classification.md` — SIMPLE / COMPLEX / AMBIGUOUS, the
  human-written-test override, and which COMPLEX signals are eligible for
  `fix_bugs`
- `${CLAUDE_PLUGIN_ROOT}/templates/github-issue-template.md` — issue body shape
- `${CLAUDE_PLUGIN_ROOT}/templates/bug-fix-pr-template.md` — bug-fix PR body shape (Step 8.5, `fix_bugs` only)
- `${CLAUDE_PLUGIN_ROOT}/scripts/resolve_owners.py` — file paths → CODEOWNERS owners (or none), and with `--github-repo`, who GitHub will accept as assignee/reviewer
- `${CLAUDE_PLUGIN_ROOT}/scripts/branch_names.py` — the name of every branch this skill creates, including ClickUp task-ID naming
- `${CLAUDE_PLUGIN_ROOT}/scripts/gh_preflight.py` — local `--live` only: GitHub access, repo, remote and PR base (Step 0)
