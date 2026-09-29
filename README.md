# Agentic QE — Claude Code Skill

A set of Claude Code skills that write unit tests, document a codebase, run
the tests, and decide what each failure means. Runs entirely inside Claude
Code — no server, no hosted service.

## Status

Under active development. See `PRD-qa-pipeline-v1.md` for the full spec and
build order. Currently in **Phase 1**: rules, the test fixture, and
`/generate-tests`.

## Skills

| Command | What it does |
|---|---|
| `/agentic-qe:generate-tests [file or folder]` | Generate unit tests for a target, matching the repo's own conventions |
| `/agentic-qe:build-context` | Build/update `.qa/context.md`, a living project overview |
| `/agentic-qe:triage-tests` | Run the suite, classify each failure as a bad test or a real bug, fix what's safe, file the rest |
| `/agentic-qe:test-pipeline` | Run all three in sequence, end to end |

## Install (one step)

This repo is packaged as a Claude Code plugin — and doubles as its own
marketplace — so anyone with access to it can install the skills into
their own Claude Code with two commands, run from anywhere (no need to
clone or `cd` into this repo first):

```
/plugin marketplace add Cognify-Analytics/Agentic-QE
/plugin install agentic-qe@agentic-qe-marketplace
```

(Or from a regular shell: `claude plugin marketplace add Cognify-Analytics/Agentic-QE`
then `claude plugin install agentic-qe@agentic-qe-marketplace`.)

That's it — the four skills are then available in **any** project as
`/agentic-qe:generate-tests`, `/agentic-qe:build-context`,
`/agentic-qe:triage-tests`, and `/agentic-qe:test-pipeline`, and Claude
will also invoke them automatically when a request matches what they do.

To pin to a specific release instead of the latest commit on `main`, add
`@<tag>` to the marketplace command, e.g.
`/plugin marketplace add Cognify-Analytics/Agentic-QE@v0.1.0`.

### Working on this repo itself

If you're developing the skills themselves (not just using them), point
Claude Code at your local checkout instead of installing from the
marketplace:

```
claude --plugin-dir .
```

Run `/reload-plugins` after editing a `SKILL.md` to pick up changes
without restarting.

## Project layout

- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — the plugin/marketplace manifests that make one-step install possible
- `skills/` — the four skills (`generate-tests`, `build-context`, `triage-tests`, `test-pipeline`)
- `rules/` — the single shared source of testing rules and conventions, read by the skills
- `templates/` — output templates (GitHub issue template, caller workflow, etc.)
- `scripts/` — helper scripts the skills shell out to
- `fixtures/` — a sample repo with known, documented bugs, used to grade `/triage-tests`
- `.github/workflows/qa-pipeline.yml` — the reusable GitHub Actions workflow (see below)

## Run it as a GitHub Action

Agentic-QE also runs unattended on pull requests via a reusable workflow
(`.github/workflows/qa-pipeline.yml`) that a small caller workflow in each
product repo invokes. The reusable workflow checks out this plugin,
installs the target repo's dependencies, decides whether the run is a
whole-repo bootstrap or an incremental run against just the PR's changed
files, and makes one call to `claude-code-action` running
`/agentic-qe:test-pipeline`. The skill does the rest exactly as it does
locally — mode, live flag, and target list all travel through
`.claude-pipeline/run.json`, which the workflow writes before the model ever
runs. Afterwards the workflow asserts no production source was touched,
posts a sticky PR comment with `summary.md`, and uploads the scratch files
as an artifact. Any SIMPLE test fixes and the updated `.qa/` folder arrive
as a PR against the developer's own branch — the pipeline never pushes to
or merges into a default branch.

### Set it up in a target repo

1. In the target repo, add these secrets: `ANTHROPIC_API_KEY` (an
   Anthropic API key), and — while this repo is private —
   `AGENTIC_QE_READ_TOKEN` (a token with read access to it).
2. Copy [`templates/qa-caller-workflow.yml`](templates/qa-caller-workflow.yml)
   into the target repo as `.github/workflows/qa.yml`, and adjust
   `setup_script` to install that repo's dependencies and test framework.
3. Turn on branch protection on the target repo's default branch before
   setting `live: true` for real — the reusable workflow can open PRs and
   file issues, and branch protection is what keeps a human in the loop for
   merges. Specifically require **at least one human approval** before
   merge, not just "require a pull request" — the pipeline's own "never
   merge" rule is necessary but not sufficient on its own; this is what
   actually enforces it at the GitHub level.
4. Trigger a first run with `workflow_dispatch` before relying on the
   `pull_request` trigger, so a whole-repo bootstrap run happens once,
   deliberately, rather than on someone's first PR.
5. **Optional — `fix_bugs`** (off by default). When on, `/triage-tests` may,
   for a narrow set of COMPLEX failures backed by a specific documented
   expectation (see `rules/error-classification.md`), write an actual fix
   to production source, verify it against the full suite, and open a
   **second PR** — separate from the routine test-fix PR — that references
   the issue already filed for that failure (`Relates to #N`, never
   auto-closing it) and is clearly marked as needing careful human review.
   The pipeline still never merges anything; this only ever produces
   something for a human to review and close themselves. It works
   independently of `live` — with `live: false` it only computes and
   reports what it would fix, which is a good way to gauge the blast
   radius before turning it on for real. Make sure step 3's branch
   protection (required human review) is in place first — a bug-fix PR
   changes production code, not just tests.

See `PLAN-github-action-v1.md` for the full design, the `run.json` schema
the workflow and skills share, and the build order this was verified
against.

## Where a run gets recorded

A run writes the same `.qa/` output whether it runs locally or in CI — what
differs is only how it persists.

**Locally**, the files land in your working tree and the pipeline reminds
you to commit them. It never commits on your behalf.

**In CI**, the runner is ephemeral, so the workflow commits `.qa/` itself
in a dedicated "Record the run in `.qa/`" step:

| Trigger | Where `.qa/` lands |
|---|---|
| `pull_request` | Committed straight onto the PR's own head branch, so the record travels with the PR and reaches your default branch when you merge it |
| `workflow_dispatch` on the default branch | Pushed to `agentic-qe/qa-baseline-<sha>` with a PR opened — the pipeline never pushes to a default branch (PRD Section 9, Rule 5) |

This happens in **report-only mode too**. Report-only means no issues are
filed and none of your code is touched; it does not mean the pipeline
withholds its own log. The step only touches `.qa/` — never source, never
tests — and runs only after the "no production source was changed"
assertion has passed. Test fixes are unaffected: they still travel in
`/triage-tests`' auto-fix PR.

Three things worth knowing:

- A push made with `GITHUB_TOKEN` does not re-trigger workflows, so this
  cannot loop.
- If someone pushes to the branch while a run is in progress, the step
  rebases onto their commit and retries rather than force-pushing.
- If `.qa/` is listed in the repo's `.gitignore`, nothing can be recorded.
  The step says so explicitly rather than reporting "no changes" — that
  entry needs removing, since `.qa/` is meant to be committed.

Getting `.qa/` into the repo is also what keeps runs cheap: without a
committed baseline, every run bootstraps the whole repo from scratch
instead of running incrementally.

## Cost and telemetry

A run's cost is driven by **token volume and turn count, not model price**.
The pipeline is built around that: most PRs change no source file, and on
those runs it now skips work rather than doing it cheaply.

**What gets skipped, and when:**

| Situation | Effect |
|---|---|
| PR changes no source file (`strategy: triage-only`) | `/generate-tests` is never invoked — the orchestrator writes its completion record directly instead of forking a subagent that would load ~15k tokens of rules to do nothing |
| No doc/manifest/schema file changed, and no new tests were written | `/build-context` is never invoked — it would otherwise regenerate all four sections from the whole repo just to discover nothing changed |
| Test suite passes cleanly | `/triage-tests` reads only the totals, never the full output — the raw log is still saved for the artifact |

`/generate-tests` also loads its rules in two tiers: the seven that decide
what gets written are always read, and the rest only when the target
actually calls for them.

**What gets measured.** Every CI run produces `telemetry.json` with cost,
turns, token usage, strategy, and which stages ran versus were skipped.
It's surfaced in three places:

- the job summary, as a table plus the full JSON
- the sticky PR comment footer (`$0.42 · 31 turns · strategy triage-only`)
- a `qa-telemetry-<run_id>` artifact, retained 90 days — longer than the
  14-day scratch artifact, because cost trends only become readable across
  dozens of runs

The committed run record in `.qa/runs/<date>-<sha>.json` carries the
strategy and per-stage outcomes too. Join it to a `telemetry.json` on
`sha` to get the full picture — the cost figures can only come from the CI
side, since a run has no way to observe its own token spend from inside.

**If you want to tune further:** the `model` input sets `--model` for the
whole pipeline. Measure before reaching for it — an Opus→Sonnet swap
observed here moved a run from $1.90 to $1.19, far less than the ~5x
price difference would suggest, which is exactly what tells you the run is
volume-bound rather than price-bound. Note also that `max_turns` is a
ceiling that stops a runaway run; lowering it does not make a normal run
cheaper.
