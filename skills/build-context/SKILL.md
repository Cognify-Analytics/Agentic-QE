---
name: build-context
description: Use when the user asks for a project context document, an architecture or schema overview, documentation of what a repository does, or a GitHub Actions QA workflow set up for the repository.
allowed-tools: Read, Write, Glob, Grep
context: fork
---

# Build Context Skill

You build and maintain two files in `.qa/`:

- `.qa/context.md` — the one document that tells later stages (especially
  `/triage-tests`) what this codebase is supposed to do.
- `.qa/github-action-qa-pipeline-template.yml` — the QA pipeline's GitHub
  Actions caller workflow with its setup already worked out for this repo
  (every stack's install steps, runtime versions). A developer copies it
  to `.github/workflows/qa.yml` and only picks the settings they want
  (`live`, `fix_bugs`, `model`, …).

You have no `Bash` and no `Edit` on purpose: you read, you write those two
files, that's it.

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

Before skipping, check one more input those files don't cover: every
`tool` in `.qa/test-inventory.json`'s `tooling_gaps` must already appear
in `.qa/context.md` (grep each one). If any doesn't, a run found a new
gap, so do not skip; take the incremental path in Step 2, where only
section 5 will differ.

Otherwise: say "Context is current (inputs unchanged)." and **stop
without reading or writing anything else** — with one exception: if
`.qa/github-action-qa-pipeline-template.yml` doesn't exist yet, skip
straight to Step 10 to create it, then stop. (Its inputs didn't change
either, so an existing one is still correct.)

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
  2. Regenerate candidate content for each of the 5 sections (Steps 4-7a,
     same as a full build).
  3. For each section, compare the freshly generated candidate against the
     section currently in the file (with `[manual]` lines spliced back in
     first, since a `[manual]` line was never something regeneration would
     reproduce on its own). A file written before section 5 existed has
     none — that counts as section 5 changing.
  4. If **3 or 4 of sections 1-4** would change, treat this the same as a
     full rebuild — approximates the PRD's "more than 30% of files changed →
     rebuild the whole document" without needing a file-count diff this
     skill has no way to compute. Section 5 is judged on its own and never
     counts toward this.
  5. If **0 sections** would change: say "Context is current." on screen and
     **do not write `context.md`** — go straight to Step 10, which decides
     separately whether the workflow template needs writing.
  6. Otherwise, update only the sections that actually changed. Leave the
     others byte-for-byte as they are.

### Step 3 — Read the test inventory

Read `.qa/test-inventory.json` if it exists. Coverage numbers for Step 7 and
the "current SHA" for the header both come from here — **never recompute
coverage yourself.** If this file doesn't exist, section 4 says so plainly
("No test inventory found — run `/generate-tests` first.") and the header's
`context_sha` is `unknown`.

Also note its `tooling_gaps`: the missing test tools later runs actually
hit, which Step 7a turns into section 5.

Check for a `stacks` object (see `/generate-tests`' multi-stack schema) —
if present, this is a monorepo with more than one independently-tested
stack (e.g. a Python backend, a TypeScript frontend); Step 7 reports each
stack's numbers separately rather than a single overall figure.

### Step 4 — Section 1: what this project does

Read the README, anything under `docs/`, the manifest's description field
(`pyproject.toml`/`package.json`/`pom.xml`'s `<description>`/etc.), and the
top-level folder layout.
Cover: what it does, who uses it (mark `[inferred]` unless an audience is
stated explicitly somewhere), and its main features.

### Step 5 — Section 2: data schema

Look for migrations, `models/`, `schema.sql`, ORM definitions, or type
files. Where these usually live per stack:

| Stack | Schema sources |
|---|---|
| Python | SQLAlchemy/Django models, Alembic/Django migrations, Pydantic models |
| JS/TS | `prisma/schema.prisma`, Drizzle `schema.ts`, TypeORM `@Entity` classes, Mongoose schemas, Zod schemas, shared `types/` |
| Java/Kotlin | JPA `@Entity` classes (`entity/`, `domain/`, `model/`), Flyway `db/migration/V*.sql`, Liquibase changelogs, records/data classes used as DTOs |

Cover the main entities, their key fields, how they relate, and cite
where you read this from. If the project has no data layer at all, say so —
"None found." is complete and correct for a project that's genuinely
stateless.

### Step 6 — Section 3: architecture

Entry points, main modules, external services, environment variables.
Typical places to find them: Next.js `app/`/`pages/` routes, route handlers
and `middleware.ts`; a Node `server.ts`/`main.ts` (Express/NestJS);
`@SpringBootApplication` classes, `@RestController`s and
`application*.yml|properties`; `.env.example` and `process.env.*` /
`@Value("${...}")` references for configuration. Same
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

### Step 7a — Section 5: test tooling requirements

Read `${CLAUDE_PLUGIN_ROOT}/rules/test-tooling-requirements.md` and follow
it. For each stack, work out what the pipeline needs (test runner, coverage
tool, DOM environment, mocking library, build settings such as Surefire's
version or Gradle's `useJUnitPlatform()`, and the runtime), which of it the
repo already has, and **the version that fits this repo**. Exact when one
package is pinned to another (`@vitest/coverage-v8` = the installed
`vitest`), the same major when they move together (`jest-environment-jsdom`
↔ `jest`), "managed by Spring Boot" when a BOM owns it. Versions come from
the lockfiles first, then the manifests.

Start from `tooling_gaps` in `.qa/test-inventory.json` (Step 3): those are
gaps `/generate-tests` or `/triage-tests` actually hit at runtime (a
coverage run that failed, modules skipped for a missing package), so every
one of them appears as ❌/⚠️ with what it broke. Everything else you can
only infer from files, so mark it accordingly (✅ only when the lockfile
shows it installed).

For every ❌/⚠️, write the fix as a single command per stack. Put Windows
PowerShell first, quoted so it pastes and runs as-is (the rule's §5 lists
what breaks), and then macOS/Linux/Git Bash. For Java/Kotlin, give the
`pom.xml`/Gradle snippet plus the command that verifies it. Runtimes
(Node/Python/JDK) use the same derivation as the workflow template in
Step 10, so the two never disagree.

Say on screen how many items are missing per stack. A developer who only
glances at the run output should still learn that section 5 has work for
them.

### Step 8 — Changelog

Append one line: date, SHA, and a specific one-line summary of what changed
this run ("first version" on the very first build; otherwise name the
section(s) updated and why).

### Step 9 — Save

Write the result to `.qa/context.md`. Confirm sections 1-4 are under the
1,500-word limit, and section 5 under its own 600, before saving — if it isn't, tighten section 1 and 3 first (they tend
to run long); coverage numbers and schema facts should never be the part
that gets cut.

### Step 10 — The repo-tuned QA workflow template

Read `${CLAUDE_PLUGIN_ROOT}/rules/qa-workflow-template.md` and
`${CLAUDE_PLUGIN_ROOT}/templates/qa-caller-workflow.yml`, then build the
candidate `.qa/github-action-qa-pipeline-template.yml` exactly as the rule
says: the generic template verbatim, with only the header, `setup_script`,
the runtime version lines and `max_turns` derived from this repo — one
install block per stack (the same stacks `.qa/test-inventory.json` lists,
or the manifest trees you found in Steps 4-6), each line traced to the file
it came from. Most of what you need (manifests, lockfiles, the repo's own
`.github/workflows/`) you already read for sections 1 and 3; read what's
missing — version files like `.nvmrc`/`.python-version`, wrapper scripts —
in one batch.

- **File doesn't exist** → write it.
- **It exists and the candidate is identical, ignoring the `(sha …)` in
  the header** → leave it alone, so an unchanged repo never gets a rewrite
  just for a new SHA.
- **It exists and differs** → overwrite it whole. It's generated, not
  hand-maintained: the developer's edits belong in their own copy at
  `.github/workflows/qa.yml`, which you never touch.

Then say on screen which it was ("Workflow template created/updated/
current"), list the stacks it sets up, and flag any stack that got the
failing placeholder (the rule's §5) — that is the line a developer must
fix before the copy will run. When this run also writes `context.md`,
mention the template in Step 8's changelog line if it was created or
updated; never rewrite `context.md` just to log a template change.

You never write to `.github/` — copying the template there is the
developer's decision, and a workflow file appearing in a PR unasked would
run with the repo's secrets.

---

## Troubleshooting

**No README, no docs, almost nothing to go on.** Write what you can from the
folder layout and manifest alone, mark it `[inferred]`, and say plainly in
section 1 that documentation was sparse — don't pad the section to look more
confident than the evidence supports.

**`.qa/test-inventory.json` missing.** Section 4 says so and stops there;
still write sections 1-3 from what's readable, and section 5 from the
manifests and lockfiles alone (there are no runtime gaps to report yet).
`context_sha` is `unknown`.

**A section would grow past what fits in 1,500 words total.** Trim prose in
sections 1/3 first. Never drop a data-schema field or a coverage number to
make room — those are the parts other skills actually rely on.

**A stack's install can't be worked out from its files** (Bun, an
unfamiliar build tool, no lockfile and no manifest). Write the failing
placeholder line from `qa-workflow-template.md` §5 for that stack and say
so — never a plausible-looking guess that would install the wrong thing.

**The repo already has `.github/workflows/qa.yml`.** Still write the
template in `.qa/`; read the existing file's `setup_script` as evidence
(`qa-workflow-template.md` §2), and if your derived setup differs, say on
screen what differs so the developer can decide whether to update their
copy. Never edit `.github/`.

**Existing `context.md` doesn't match the template shape at all** (e.g. a
human wrote something free-form before this skill ever ran). Don't force a
partial/incremental update onto a document that isn't in the expected shape
— treat it as if the file didn't exist (full build), but preserve any
`[manual]`-marked lines you can find first.

---

## Rules reference

- `${CLAUDE_PLUGIN_ROOT}/rules/context-file-template.md` — the exact shape, and the
  `[inferred]`/`[manual]` conventions
- `${CLAUDE_PLUGIN_ROOT}/rules/test-tooling-requirements.md` — section 5:
  what each stack needs, version derivation, PowerShell-safe install steps
- `${CLAUDE_PLUGIN_ROOT}/rules/qa-workflow-template.md` — how the repo-tuned
  workflow template is derived (Step 10)
- `${CLAUDE_PLUGIN_ROOT}/templates/qa-caller-workflow.yml` — the generic
  caller workflow the template is built from
