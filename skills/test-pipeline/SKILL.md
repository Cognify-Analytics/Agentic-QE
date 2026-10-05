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
Pass `--fix-bugs` to also turn on `/triage-tests`' opt-in bug-fix mode
(off by default — see its Step 7.5/8.5 and PRD Section 9.1); this works
independently of `--live` per that skill's own rules. Anything else in
`$ARGUMENTS` is forwarded to `/generate-tests` as its target (a file or
folder) — with no target, it scans the whole repo per its own Step 5
ranking.

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
2. **Local `--live` runs only — check GitHub access before Stage 1.** In
   CI the workflow supplies the token, the repo, and a PR base branch that
   is known to exist on the remote. Locally none of that is given, so
   establish it now rather than let `/triage-tests` discover a problem
   after two whole stages have already run. Run
   `python ${CLAUDE_PLUGIN_ROOT}/scripts/gh_preflight.py` (it checks `gh`
   is installed and logged in, resolves the repo from the branch's remote,
   checks you have write access, and picks the PR base — see the script's
   docstring for the rule).
   - **`"ok": true`** — copy everything except `ok`/`problems` into
     `run.json` as a `"local"` object (schema below) when you write it in
     step 5.
   - **`"ok": false`** — **stop before writing anything else.** Show the
     user every entry in `problems` and say they can fix those and re-run,
     or re-run without `--live` for a report-only run. Never quietly drop
     to report-only: they asked for live and should know they aren't
     getting it.

   Report-only local runs and CI runs skip this step — neither one needs
   to reach GitHub from this machine.
3. Create `.qa/` if it doesn't exist.
4. Create `.claude-pipeline/` if it doesn't exist.
5. **Check for a CI-written `run.json` first.** If `.claude-pipeline/run.json`
   already exists and its `"mode"` is `"ci"`, the GitHub Actions workflow
   wrote it before invoking this skill (see the CI schema below) — **read it
   and do not overwrite it.** Everything downstream (stage checks, the
   summary, the run record) works exactly the same regardless of which
   schema produced the file. Otherwise (a local, interactive run), write
   `.claude-pipeline/run.json` yourself now (schema below) — **before
   invoking any stage**, since that's how `/generate-tests` knows to skip
   its approval prompt and how `/triage-tests` knows whether to run live.
6. **Skip this step entirely in CI mode** (i.e. when `run.json`'s `"mode"`
   is `"ci"`) — the workflow already keeps `.claude-pipeline/` out of the
   diff via `.git/info/exclude`, and appending to a tracked `.gitignore` on
   every CI run would dirty the working tree for no reason. For a local
   run: ensure `.gitignore` has a `.claude-pipeline/` line (add it if
   missing; create `.gitignore` if the repo has none). A one-liner is
   enough:
   `grep -qxF '.claude-pipeline/' .gitignore 2>/dev/null || echo '.claude-pipeline/' >> .gitignore`
7. Ensure `.gitignore` does **not** ignore `.qa/` — that folder is meant to
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
  "live": false,
  "fix_bugs": false
}
```

**Local `--live` run** — the same, plus the `"local"` object from step 2's
preflight. It is the local stand-in for the CI schema's `ci` block:
`/triage-tests` reads `repo` where CI would read `GH_REPO`,
`pr_base_branch` where CI would read `ci.pr_base_branch`, and
`start_branch` to put the developer back where they started once it has
finished pushing fix branches.

```json
{
  "sha": "a1b2c3d",
  "branch": "feature/refunds",
  "timestamp": "2026-08-21T14:02:00Z",
  "mode": "pipeline",
  "live": true,
  "fix_bugs": false,
  "local": {
    "repo": "org/repo",
    "remote": "origin",
    "default_branch": "main",
    "start_branch": "feature/refunds",
    "pr_base_branch": "feature/refunds"
  }
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
  "fix_bugs": false,
  "ci": {
    "pr_number": 42,
    "pr_base_branch": "feature/refunds",
    "run_url": "https://github.com/org/repo/actions/runs/123",
    "strategy": "incremental",
    "targets": ["src/orders.py", "src/pricing.py"],
    "context_inputs_changed": true
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

`ci.context_inputs_changed` is the workflow's answer to "did any file
`/build-context` reads from change in this PR?" — docs, manifests, schema
and model files. `false` is what lets Stage 2 be skipped outright (see
Stage 2 for the other two conditions that must hold alongside it). It is
deliberately conservative: when the workflow can't compute a base diff at
all (e.g. `workflow_dispatch`), it reports `true` and nothing is skipped.
A missing field means `true` — never treat absence as permission to skip.

---

## Stage 1 — `/generate-tests`

**Skip the invocation entirely when this is a CI run whose `ci.strategy` is
`"triage-only"`.** That strategy means the workflow already proved this PR
changed no source file, so `/generate-tests` has nothing to generate — and
forking a subagent that reads every rule file before deciding to write
nothing is the most expensive no-op in this pipeline. Write its completion
record yourself instead (you have `Write`), then go straight to Stage 2:

```json
{
  "status": "ok",
  "git_sha": "<sha from run.json>",
  "files_created": [],
  "files_modified": [],
  "modules_skipped": [],
  "tests_removed": [],
  "tests_flagged_as_possible_bugs": [],
  "notes": "Triage-only run — no source files changed, so /generate-tests was not invoked. Stage skipped by the orchestrator."
}
```

This is the same `"status": "ok"` shape `/generate-tests` would have
written for a triage-only run itself (its Step 5), so every downstream
reader — the check below, `summary.md`, the run record — behaves exactly as
before. Record it as `"skipped:triage-only"` in `stages.json` (see Finish).

Otherwise, invoke it with the Skill tool (forwarding any target from
`$ARGUMENTS`).

**Check before continuing:**
- Does `.claude-pipeline/01-tests.json` exist, and is its `"status"` not
  `"failed"`?
- **Unless this is a CI run with `ci.strategy` `"triage-only"`** (in which
  case nothing was generated and `.qa/` is unchanged by design — whether
  you wrote the stub above or `/generate-tests` stopped at its own Step 0
  — so skip this second check): has `.qa/test-inventory.json` actually
  been updated (its `last_updated_sha` matches this run's `sha` from
  `run.json`)?

**If either applicable check fails: stop the whole pipeline right here.**
Do not run Stage 2 or 3. Report exactly which check failed and show
whatever `01-tests.json` does contain (even a `"status": "partial"` file
has useful detail). This is the check the PRD calls out by name — a silent
failure here would hand Stage 2 nothing to document and Stage 3 nothing
real to triage.

## Stage 2 — `/build-context`

**Skip the invocation entirely when all three of these hold:**

1. This is a CI run and `run.json`'s `ci.context_inputs_changed` is
   `false` — the workflow diffed the PR and found no doc, manifest, or
   schema file changed, so sections 1-3 of `context.md` cannot have
   changed.
2. `.qa/context.md` already exists and has real content (the same check
   you would otherwise run *after* the stage).
3. Stage 1 changed nothing — `01-tests.json`'s `files_created` and
   `files_modified` are both empty. New tests move coverage, coverage is
   section 4, and this condition is what stops a skipped Stage 2 from
   leaving a stale number behind.

If all three hold: say "Context is current (inputs unchanged — stage
skipped)." on screen, leave `.qa/context.md` byte-for-byte alone, record
`"skipped:inputs-unchanged"` in `stages.json`, and move to Stage 3. Do not
invoke the skill. Without this gate the skill regenerates all four
sections from the whole repo on every run just to discover nothing
changed — correct, but the most expensive possible way to reach that
answer.

If any one of them does not hold, invoke it with the Skill tool. No target
to forward — it always looks at the whole repo.

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

## If you stop early at a stage gate

A halted run is still a run, and it is the one most worth having a record
of. Before stopping at any gate above, write both:

1. `.claude-pipeline/stages.json` — the stages that ran, and
   `"not_reached"` for the rest.
2. `.qa/runs/<yyyy-mm-dd>-<sha>.json` — the same run record as a normal
   finish (schema below), with `"status": "stopped"`, a `"stopped_at"`
   naming the gate that failed (e.g. `"stage-1-check"`), and a one-line
   `"reason"`. Fill in whatever is genuinely known and leave the rest out
   rather than guessing at numbers no stage produced.

Then report what failed on screen and stop. In CI the workflow commits
that record the same way it would a successful run, so a halted run is
visible in the repo rather than only in a job log that ages out.

---

## Finish

1. **Write `.claude-pipeline/stages.json` first** (shape below) — before the
   summary, so it survives even if a later step here fails. This is the
   only record of which stages actually ran versus were skipped, and the
   workflow's telemetry step reads it to fold that into the run's cost
   data. **If the pipeline stops early at any stage gate above, write this
   file before stopping**, with the stages that did run and
   `"not_reached"` for the rest.
2. Read `run.json`, `01-tests.json`, `.qa/context.md`, and `03-triage.json`.
3. Write `.claude-pipeline/summary.md` (shape below).
4. Copy a compact run record to `.qa/runs/<yyyy-mm-dd>-<sha>.json` — not the
   full scratch detail, just enough for a team to see pipeline history at a
   glance (see schema below). Create `.qa/runs/` if it doesn't exist.
5. **Local runs only** — remind the developer on screen to commit
   `.qa/context.md`, `.qa/test-inventory.json`, `.qa/runs/<...>.json`, and
   every test file `01-tests.json` listed under
   `files_created`/`files_modified`. Locally this pipeline never commits on
   its own (Section 9, Rule 5/6 — commits and merges are for people).
   **Exception, local `--live` only:** leave out any test file listed in
   `03-triage.json`'s `pr_planned.files_changed` when `pr_url` is set —
   that file was committed to the auto-fix branch and travels in that PR,
   exactly as in CI. Name the PR instead so the developer knows where it
   went.

   **In CI mode, do not print that reminder** — there is no developer at a
   terminal to act on it, and the workflow's "Record the run in `.qa/`"
   step commits `.qa/` itself once every stage has finished. Say where it
   landed instead: on the PR's own head branch. Test files still travel in
   `/triage-tests`' auto-fix PR, as before.

**Expected — `.claude-pipeline/stages.json` (scratch, read by CI telemetry):**

```json
{
  "generate_tests": "skipped:triage-only",
  "build_context": "skipped:inputs-unchanged",
  "triage_tests": "ran"
}
```

Each value is one of `"ran"`, `"not_reached"` (the pipeline stopped before
it), or `"skipped:<reason>"` — use exactly `"skipped:triage-only"` (Stage 1)
and `"skipped:inputs-unchanged"` (Stage 2) for the two gates above, so runs
stay comparable to each other over time. Do not invent new reason strings
for those two cases.

**Expected — `.claude-pipeline/summary.md`:**

```markdown
# QA Pipeline Run — {project name}
Started {timestamp} | SHA {sha} | branch {branch} | mode {report-only|live}
{strategy, and any stage that was skipped, with its reason}

## Tests
{files created/modified from 01-tests.json, coverage before -> after}
{tests_flagged_as_possible_bugs count, if any, called out by name}

## Context
{"context is current" or which sections were updated}

## Failures
{totals from 03-triage.json: passed/failed, SIMPLE fixed count, COMPLEX/AMBIGUOUS count}

## Needs a human
{one line per issue in issues_created/issues_commented, report-only or real URL}
{one line per entry in bug_fix_prs_created, flagged distinctly — e.g. "Bug-fix PR (needs careful review): ..." — since this is a production-code change, not a routine test fix}

## Changes made
{pr_planned or pr_url — "no source code changed" unless bug_fix_prs_created is non-empty, in which case say explicitly that fix_bugs was on and list each bug-fix PR with the issue it relates to}

## Please commit
{local runs: the exact file list from step 5 above}
{CI runs: replace this section with "## Recorded" — say that `.qa/` was committed to the PR's head branch by the workflow, and name any test files travelling in the auto-fix PR}
```

**Expected — `.qa/runs/<yyyy-mm-dd>-<sha>.json`:**

```json
{
  "date": "2026-08-21",
  "sha": "a1b2c3d",
  "branch": "feature/refunds",
  "mode": "report-only",
  "strategy": "incremental",
  "stages": {
    "generate_tests": "ran",
    "build_context": "ran",
    "triage_tests": "ran"
  },
  "coverage": { "before": 51.0, "after": 67.4 },
  "tests_created": 2,
  "tests_modified": 1,
  "tests_flagged_as_possible_bugs": 1,
  "context_action": "updated section 4",
  "triage_totals": { "tests": 84, "passed": 79, "failed": 5 },
  "simple_fixes": 1,
  "complex_issues": 2,
  "bug_fix_prs": 0,
  "caps_hit": []
}
```

`bug_fix_prs` is the count of `bug_fix_prs_created` entries with a non-null
`pr_url` (i.e. actually opened, not report-only) — always `0` unless
`fix_bugs` was on for this run.

`strategy` and `stages` mirror what you wrote to `stages.json`, and are the
durable half of this pipeline's telemetry: `.qa/runs/` is committed, so
these accumulate into real history a team can look back over, while the
cost figures live only in the CI run (you have no way to see your own token
spend from inside the run). Pair them by `sha` when analyzing — that's the
join key between a run record here and a `telemetry.json` from CI.

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
