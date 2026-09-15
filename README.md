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
   merges.
4. Trigger a first run with `workflow_dispatch` before relying on the
   `pull_request` trigger, so a whole-repo bootstrap run happens once,
   deliberately, rather than on someone's first PR.

See `PLAN-github-action-v1.md` for the full design, the `run.json` schema
the workflow and skills share, and the build order this was verified
against.
