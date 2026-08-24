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
| `/generate-tests [file or folder]` | Generate unit tests for a target, matching the repo's own conventions |
| `/build-context` | Build/update `.qa/context.md`, a living project overview |
| `/triage-tests` | Run the suite, classify each failure as a bad test or a real bug, fix what's safe, file the rest |
| `/test-pipeline` | Run all three in sequence, end to end |

## Installing locally

This is currently a local-only project (no GitHub repo yet). To use the
skills in this repo with Claude Code, they load automatically from
`.claude/skills/` when Claude Code is run from this directory. Once this
project moves to GitHub, teammates will be able to clone the repo and get
the skills the same way — no separate install step, since skills in
`.claude/skills/` are picked up automatically by Claude Code. A packaged
plugin distribution is planned for a later phase.

## Project layout

- `.claude/skills/` — the four skills (`generate-tests`, `build-context`, `triage-tests`, `test-pipeline`)
- `rules/` — the single shared source of testing rules and conventions, read by the skills
- `templates/` — output templates (GitHub issue template, etc.)
- `scripts/` — helper scripts the skills shell out to
- `fixtures/` — a sample repo with known, documented bugs, used to grade `/triage-tests`
