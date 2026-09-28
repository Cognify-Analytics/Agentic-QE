---
name: build-context
description: Use when the user asks for a project context document, an architecture or schema overview, or documentation of what a repository does.
allowed-tools: Read, Write, Glob, Grep
context: fork
---

# Build Context Skill

You build and maintain `.qa/context.md` — the one document that tells later
stages (especially `/triage-tests`) what this codebase is supposed to do.
You have no `Bash` and no `Edit` on purpose: you read, you write one file,
that's it.

**Arguments, if given:** $ARGUMENTS — pass `--rebuild` to force a full
rebuild regardless of what's already there.

## Why no Bash means no `git diff`

This skill can't shell out, so it can't run `git diff` to see what changed
since the last build. The incremental-update logic below is built around
that constraint deliberately — it re-reads the small set of source
locations every time and diffs the *freshly generated content* against
what's currently in `.qa/context.md`, rather than trying to infer "what
category of file changed" from git history it can't see.

That regenerate-then-diff pass is correct but not free: on a large repo it
is the most expensive way to reach the answer "nothing changed." Step 0 is
what avoids paying for it, using a diff computed upstream by something that
*does* have git — the CI workflow. This still satisfies the actual requirement (unchanged repo → "context
is current", no rewrite) without needing Bash. The "current SHA" stamped
into the file comes from `.qa/test-inventory.json`'s `last_updated_sha` (that
file's own skill, `/generate-tests`, does have Bash and stamps a real SHA)
— not from running git directly.

---

## Instructions

### Step 0 — In CI, check whether anything you read from even changed

**Do this before Step 1, and only when `.claude-pipeline/run.json` exists
with `"mode": "ci"`.** If that file's `ci.context_inputs_changed` is
`false`, the workflow diffed the PR and found no doc, manifest, schema or
model file changed — the only inputs sections 1-3 are built from. Combined
with an existing `.qa/context.md`, that means regenerating those sections
could not produce anything different.

In that case: say "Context is current (inputs unchanged)." and **stop
without reading or writing anything else.**

Two guards on this. `--rebuild` always wins — it forces the full path
regardless. And a missing field means *changed*: only an explicit `false`
lets you skip, so a stale or hand-written `run.json` can never silently
suppress a rebuild.

This is a backstop. In a normal CI run `/test-pipeline` doesn't invoke you
at all when this holds (its Stage 2 gate also checks that no new tests were
written, which it can see and you can't) — this step only catches a direct
invocation.

### Step 1 — Read the template

Read `${CLAUDE_PLUGIN_ROOT}/rules/context-file-template.md`. It fixes the exact shape of the
output — section order, the `[inferred]`/`[manual]` conventions, the word
limit. Every run must produce something matching that shape.

### Step 2 — Decide: full build, forced rebuild, or incremental update

- `.qa/context.md` **doesn't exist** → full build (go to Step 4).
- It exists and `--rebuild` was passed → full build (go to Step 4).
- It exists → **incremental path**:
  1. Read the existing file. Note every line containing `[manual]` — these
     survive no matter what.
  2. Regenerate candidate content for each of the 4 sections (Steps 4-7,
     same as a full build).
  3. For each section, compare the freshly generated candidate against the
     section currently in the file (with `[manual]` lines spliced back in
     first, since a `[manual]` line was never something regeneration would
     reproduce on its own).
  4. If **3 or 4 of the 4 sections** would change, treat this the same as a
     full rebuild — approximates the PRD's "more than 30% of files changed →
     rebuild the whole document" without needing a file-count diff this
     skill has no way to compute.
  5. If **0 sections** would change: say "Context is current." on screen and
     **stop — do not write the file.**
  6. Otherwise, update only the sections that actually changed. Leave the
     others byte-for-byte as they are.

### Step 3 — Read the test inventory

Read `.qa/test-inventory.json` if it exists. Coverage numbers for Step 7 and
the "current SHA" for the header both come from here — **never recompute
coverage yourself.** If this file doesn't exist, section 4 says so plainly
("No test inventory found — run `/generate-tests` first.") and the header's
`context_sha` is `unknown`.

Check for a `stacks` object (see `/generate-tests`' multi-stack schema) —
if present, this is a monorepo with more than one independently-tested
stack (e.g. a Python backend, a TypeScript frontend); Step 7 reports each
stack's numbers separately rather than a single overall figure.

### Step 4 — Section 1: what this project does

Read the README, anything under `docs/`, the manifest's description field
(`pyproject.toml`/`package.json`/etc.), and the top-level folder layout.
Cover: what it does, who uses it (mark `[inferred]` unless an audience is
stated explicitly somewhere), and its main features.

### Step 5 — Section 2: data schema

Look for migrations, `models/`, `schema.sql`, ORM definitions, or type
files. Cover the main entities, their key fields, how they relate, and cite
where you read this from. If the project has no data layer at all, say so —
"None found." is complete and correct for a project that's genuinely
stateless.

### Step 6 — Section 3: architecture

Entry points, main modules, external services, environment variables. Same
rule: "None found." is a valid answer for any of these if the project
genuinely has none — do not invent an entry point, a database, or an env
var that isn't there just because the PRD's own worked example has one.

### Step 7 — Section 4: test coverage

Pull every number from `.qa/test-inventory.json` (Step 3) — overall
coverage, per-module coverage bucketed into well/weakly/not-covered,
framework, test location, and any `skipped_reason` entries as "known gaps."

**Multi-stack (`stacks` present):** report this per stack — a "Backend
(pytest)" subsection and a "Frontend (jest)" subsection (or whatever the
stacks are named), each with its own overall coverage, framework, test
location, and known gaps. Do not average or sum the stacks into one
number; a combined "60% coverage" figure across two unrelated codebases
and frameworks is not a number anyone can act on.

### Step 8 — Changelog

Append one line: date, SHA, and a specific one-line summary of what changed
this run ("first version" on the very first build; otherwise name the
section(s) updated and why).

### Step 9 — Save

Write the result to `.qa/context.md`. Confirm it's under the 1,500-word
limit before saving — if it isn't, tighten section 1 and 3 first (they tend
to run long); coverage numbers and schema facts should never be the part
that gets cut.

---

## Troubleshooting

**No README, no docs, almost nothing to go on.** Write what you can from the
folder layout and manifest alone, mark it `[inferred]`, and say plainly in
section 1 that documentation was sparse — don't pad the section to look more
confident than the evidence supports.

**`.qa/test-inventory.json` missing.** Section 4 says so and stops there;
still write sections 1-3 from what's readable. `context_sha` is `unknown`.

**A section would grow past what fits in 1,500 words total.** Trim prose in
sections 1/3 first. Never drop a data-schema field or a coverage number to
make room — those are the parts other skills actually rely on.

**Existing `context.md` doesn't match the template shape at all** (e.g. a
human wrote something free-form before this skill ever ran). Don't force a
partial/incremental update onto a document that isn't in the expected shape
— treat it as if the file didn't exist (full build), but preserve any
`[manual]`-marked lines you can find first.

---

## Rules reference

- `${CLAUDE_PLUGIN_ROOT}/rules/context-file-template.md` — the exact shape, and the
  `[inferred]`/`[manual]` conventions
