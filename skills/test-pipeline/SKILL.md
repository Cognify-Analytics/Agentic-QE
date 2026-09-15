---
name: test-pipeline
description: Use when the user asks to run the full QA pipeline, audit test health end to end, or set up testing for a repository.
allowed-tools: Read, Write, Bash, Skill
---

# Test Pipeline Skill

You run `/generate-tests`, `/build-context`, and `/triage-tests` in
sequence, checking after each one that it actually produced valid output
before letting the next stage rely on it. You are **not forked** — you run
in the developer's main session so they can watch each stage happen.

**Arguments, if given:** $ARGUMENTS — pass `--live` to run `/triage-tests`
in live mode (real branches/PRs/issues) instead of the default report-only.
Anything else in `$ARGUMENTS` is forwarded to `/generate-tests` as its
target (a file or folder) — with no target, it scans the whole repo per its
own Step 5 ranking.

This skill also runs unattended inside CI, driven by a GitHub Actions
reusable workflow that writes `.claude-pipeline/run.json` itself before
invoking `/agentic-qe:test-pipeline` (see "Before starting" below, and the
CI `run.json` schema). In that mode you are **not** forked either — same
single-session behavior, just non-interactive.

---

## Before starting

1. **Check this is a git repo.** Run `git rev-parse --is-inside-work-tree`.
   If it fails, **stop immediately** and tell the user: this pipeline needs
   git for the SHA/branch stamped into every output file and for the
   `auto-fix/triage-<sha>` branch `/triage-tests` creates for SIMPLE fixes
   (Section 9, Rule 3/5) — there is no reasonable way to run safely without
   it. Suggest `git init` and an initial commit, then stop. Do not create
   any other file yet.
2. Create `.qa/` if it doesn't exist.
3. Create `.claude-pipeline/` if it doesn't exist.
4. **Check for a CI-written `run.json` first.** If `.claude-pipeline/run.json`
   already exists and its `"mode"` is `"ci"`, the GitHub Actions workflow
   wrote it before invoking this skill (see the CI schema below) — **read it
   and do not overwrite it.** Everything downstream (stage checks, the
   summary, the run record) works exactly the same regardless of which
   schema produced the file. Otherwise (a local, interactive run), write
   `.claude-pipeline/run.json` yourself now (schema below) — **before
   invoking any stage**, since that's how `/generate-tests` knows to skip
   its approval prompt and how `/triage-tests` knows whether to run live.
5. **Skip this step entirely in CI mode** (i.e. when `run.json`'s `"mode"`
   is `"ci"`) — the workflow already keeps `.claude-pipeline/` out of the
   diff via `.git/info/exclude`, and appending to a tracked `.gitignore` on
   every CI run would dirty the working tree for no reason. For a local
   run: ensure `.gitignore` has a `.claude-pipeline/` line (add it if
   missing; create `.gitignore` if the repo has none). A one-liner is
   enough:
   `grep -qxF '.claude-pipeline/' .gitignore 2>/dev/null || echo '.claude-pipeline/' >> .gitignore`
6. Ensure `.gitignore` does **not** ignore `.qa/` — that folder is meant to
   be committed (Section 6.1). If you find a `.qa` or `.qa/` line in
   `.gitignore`, remove it and tell the user why: their test inventory and
   context doc would otherwise never make it into version control and the
   next run would look like a first run to every teammate.

**Expected — `.claude-pipeline/run.json` (local, interactive run):**

```json
{
  "sha": "a1b2c3d",
  "branch": "feature/refunds",
  "timestamp": "2026-08-21T14:02:00Z",
  "mode": "pipeline",
  "live": false
}
```

**Expected — `.claude-pipeline/run.json` (CI run, written by the workflow
before this skill is invoked — see this repo's
`.github/workflows/qa-pipeline.yml`):**

```json
{
  "sha": "a1b2c3d",
  "branch": "feature/refunds",
  "timestamp": "2026-09-09T14:02:00Z",
  "mode": "ci",
  "live": true,
  "ci": {
    "pr_number": 42,
    "pr_base_branch": "feature/refunds",
    "run_url": "https://github.com/org/repo/actions/runs/123",
    "strategy": "incremental",
    "targets": ["src/orders.py", "src/pricing.py"]
  }
}
```

`ci.strategy` is `bootstrap` | `incremental` | `triage-only`. `ci.targets`
is the exact file list `/generate-tests` should test — non-empty means
incremental (test exactly those files); empty means either whole-repo
(`ci.strategy` is `bootstrap`) or nothing at all (`ci.strategy` is
`triage-only` — `.qa/` already has a baseline and this run touched no
source, so `/generate-tests` writes nothing and only `/triage-tests` does
real work). `ci.pr_base_branch` is where `/triage-tests` should base its
auto-fix PR — always the PR's own head branch, never the repo's default
branch, so the fix flows back into the developer's own PR.

---

## Stage 1 — `/generate-tests`

Invoke it with the Skill tool (forwarding any target from `$ARGUMENTS`).

**Check before continuing:**
- Does `.claude-pipeline/01-tests.json` exist, and is its `"status"` not
  `"failed"`?
- **Unless this is a CI run with `ci.strategy` `"triage-only"`** (in which
  case `/generate-tests` deliberately wrote nothing and `.qa/` is
  unchanged by design — skip this second check): has
  `.qa/test-inventory.json` actually been updated (its `last_updated_sha`
  matches this run's `sha` from `run.json`)?

**If either applicable check fails: stop the whole pipeline right here.**
Do not run Stage 2 or 3. Report exactly which check failed and show
whatever `01-tests.json` does contain (even a `"status": "partial"` file
has useful detail). This is the check the PRD calls out by name — a silent
failure here would hand Stage 2 nothing to document and Stage 3 nothing
real to triage.

## Stage 2 — `/build-context`

Invoke it with the Skill tool. No target to forward — it always looks at
the whole repo.

**Check before continuing:** does `.qa/context.md` exist and have content
(not just a header with empty sections)? Note: if `/build-context` correctly
determined nothing needed to change and reported "context is current," the
existing file having content still satisfies this check — that's success,
not failure.

**If the check fails: stop.** Do not run Stage 3 against a missing or
empty context document — `/triage-tests` explicitly depends on it to judge
whether a failure is a real bug.

## Stage 3 — `/triage-tests`

Invoke it with the Skill tool. Live/report-only mode was already decided
in `run.json` before Stage 1 ever ran — `/triage-tests` reads that itself,
you don't need to re-specify it here.

**Check before continuing:** does `.claude-pipeline/03-triage.json` exist?

**If the check fails: stop and report.** (There is no Stage 4 to protect,
but the run is still incomplete — don't write a summary claiming triage
happened if it didn't produce output.)

---

## Finish

1. Read `run.json`, `01-tests.json`, `.qa/context.md`, and `03-triage.json`.
2. Write `.claude-pipeline/summary.md` (shape below).
3. Copy a compact run record to `.qa/runs/<yyyy-mm-dd>-<sha>.json` — not the
   full scratch detail, just enough for a team to see pipeline history at a
   glance (see schema below). Create `.qa/runs/` if it doesn't exist.
4. Remind the developer on screen to commit `.qa/context.md`,
   `.qa/test-inventory.json`, `.qa/runs/<...>.json`, and every test file
   `01-tests.json` listed under `files_created`/`files_modified`. This
   pipeline never commits on its own (Section 9, Rule 5/6 — commits and
   merges are for people).

**Expected — `.claude-pipeline/summary.md`:**

```markdown
# QA Pipeline Run — {project name}
Started {timestamp} | SHA {sha} | branch {branch} | mode {report-only|live}

## Tests
{files created/modified from 01-tests.json, coverage before -> after}
{tests_flagged_as_possible_bugs count, if any, called out by name}

## Context
{"context is current" or which sections were updated}

## Failures
{totals from 03-triage.json: passed/failed, SIMPLE fixed count, COMPLEX/AMBIGUOUS count}

## Needs a human
{one line per issue in issues_created/issues_commented, report-only or real URL}

## Changes made
{pr_planned or pr_url — always "no source code changed"}

## Please commit
{the exact file list from step 4 above}
```

**Expected — `.qa/runs/<yyyy-mm-dd>-<sha>.json`:**

```json
{
  "date": "2026-08-21",
  "sha": "a1b2c3d",
  "branch": "feature/refunds",
  "mode": "report-only",
  "coverage": { "before": 51.0, "after": 67.4 },
  "tests_created": 2,
  "tests_modified": 1,
  "tests_flagged_as_possible_bugs": 1,
  "context_action": "updated section 4",
  "triage_totals": { "tests": 84, "passed": 79, "failed": 5 },
  "simple_fixes": 1,
  "complex_issues": 2,
  "caps_hit": []
}
```

**Multi-stack repos** (`01-tests.json`/`03-triage.json` have a `stacks`
shape — see `/generate-tests`): report coverage and triage totals **per
stack**, both in `summary.md`'s "## Tests"/"## Failures" sections and in
this run record's `coverage`/`triage_totals` fields — replace each with an
object keyed by stack name (e.g. `"coverage": { "backend": {"before":
23.9, "after": 44.9}, "frontend": {"before": 30.1, "after": 73.1} }`).
Never collapse two stacks into one combined number.

---

## Troubleshooting

**Not a git repo.** Stop before creating anything (see Before Starting,
step 1). This is the one failure mode that blocks the pipeline before it
even starts, rather than between stages.

**Stage 1 fails (no test framework detected, or it stops for any other
reason).** Report it and stop — this is the "deliberately breaking stage 1"
case the PRD's Phase 4 finish criterion names directly. Stage 2 and 3 must
never run against a repo that Stage 1 gave up on.

**Stage 2 says "context is current" every time even after real changes.**
That's a `/build-context` bug, not something to work around here — report
it, don't force a rebuild yourself by deleting `.qa/context.md`.

**A stage's own skill invocation errors out entirely** (crashes rather than
writing a `"status": "failed"`/partial file). Treat it the same as a failed
check — stop, report what's known, do not guess at what the missing stage
would have produced.
