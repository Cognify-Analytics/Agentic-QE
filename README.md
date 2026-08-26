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
- `templates/` — output templates (GitHub issue template, etc.)
- `scripts/` — helper scripts the skills shell out to
- `fixtures/` — a sample repo with known, documented bugs, used to grade `/triage-tests`
