# Agentic QE — Claude Code Skill

A set of Claude Code skills that write unit tests, document a codebase, run
the tests, and decide what each failure means. Runs entirely inside Claude
Code — no server, no hosted service. Use it from your own terminal, or let
a GitHub Action run it on every pull request.

## Status

Version **0.2.0**, under active development. All four skills and the
reusable GitHub Actions workflow are built. Everything defaults to
**report-only**: issues and PRs are drafted in full but never filed until
you turn on `--live` (locally) or `live: true` (in CI). See
`PRD-qa-pipeline-v1.md` for the full spec and `PLAN-github-action-v1.md`
for the CI design.

## Skills

| Command | What it does |
|---|---|
| `/agentic-qe:generate-tests [file or folder]` | Generate unit tests for a target, matching the repo's own conventions |
| `/agentic-qe:build-context` | Build/update `.qa/context.md`, a living project overview |
| `/agentic-qe:triage-tests [--live] [--fix-bugs]` | Run the suite, classify each failure as a bad test or a real bug, fix what's safe, file issues for the rest |
| `/agentic-qe:test-pipeline [--live] [--fix-bugs] [file or folder]` | Run all three in sequence, end to end |

| Flag | Effect |
|---|---|
| *(none)* | Report-only. Every issue and PR is drafted in `.claude-pipeline/03-triage.json`, and nothing reaches GitHub |
| `--live` | Actually file issues and open PRs (see [Filing issues and PRs from your machine](#filing-issues-and-prs-from-your-machine)) |
| `--clickup-branches` | Opt-in. Names every branch the pipeline pushes after your branch's ClickUp task ID (see [ClickUp branch naming](#clickup-branch-naming--opt-in)) |
| `--fix-bugs` | Opt-in. Lets triage attempt a narrow, verified fix to production source for some real bugs (see [`fix_bugs`](#fix_bugs--opt-in-bug-fix-prs)). Without `--live`, it only reports what it would change |

## Install

You only do this once per computer. It takes about 5 minutes.

### What you need before you start

- **Claude Code** installed and working. If typing `claude` in a terminal
  opens it, you're good.
- **A GitHub account in the Cognify-Analytics org.** This repo is
  private. If you can't open
  <https://github.com/Cognify-Analytics/Agentic-QE> in your browser, ask
  an org admin to add you first. None of the steps below will work until
  you can.

### Step 1 — Install the GitHub CLI

Claude Code downloads the plugin straight from GitHub, so your computer
has to be logged in to GitHub. The GitHub CLI (`gh`) is the easiest way
to do that.

Open a terminal and run the command for your system:

| System | Command |
|---|---|
| Windows | `winget install --id GitHub.cli` |
| macOS | `brew install gh` |
| Linux | Follow <https://github.com/cli/cli#installation> |

Then **close the terminal and open a new one**, so it can find `gh`.

### Step 2 — Log in to GitHub

1. Run:
   ```
   gh auth login
   ```
2. Answer its questions like this:
   - *Where do you use GitHub?* → **GitHub.com**
   - *What is your preferred protocol?* → **HTTPS**
   - *Authenticate Git with your GitHub credentials?* → **Yes**
   - *How would you like to authenticate?* → **Login with a web browser**
3. It shows a one-time code. Press Enter, paste the code into the browser
   page that opens, and approve.
4. Run this once, so git uses the same login:
   ```
   gh auth setup-git
   ```

### Step 3 — Check you can reach the repo

Run:

```
git ls-remote https://github.com/Cognify-Analytics/Agentic-QE.git
```

- **You see lines of letters and numbers:** it works. Go to Step 4.
- **You see an error, or it asks for a password:** stop here and see
  [If something goes wrong](#if-something-goes-wrong).

### Step 4 — Install the plugin

1. Start Claude Code (from any folder):
   ```
   claude
   ```
2. Type these two commands into Claude Code, one at a time:
   ```
   /plugin marketplace add Cognify-Analytics/Agentic-QE
   /plugin install agentic-qe@agentic-qe-marketplace
   ```
3. Quit Claude Code and start it again.

### Step 5 — Check it worked

In Claude Code, type `/agentic-qe:` and you should see four commands:

- `/agentic-qe:generate-tests`
- `/agentic-qe:build-context`
- `/agentic-qe:triage-tests`
- `/agentic-qe:test-pipeline`

You're done. The commands now work in every project on this computer, and
they update themselves. Next: [Run it locally](#run-it-locally).

### If something goes wrong

| What you see | What to do |
|---|---|
| `gh: command not found` or `'gh' is not recognized` | Close the terminal and open a new one. Still failing? Redo Step 1. |
| Step 3 fails, or Claude Code says `Failed to clone marketplace repository` | Make sure you can open the repo in your browser (you must be in the org). Then redo Step 2. |
| `SSH authentication failed` | Claude Code tried an old SSH key instead of your Step 2 login. Set the environment variable `CLAUDE_CODE_PLUGIN_PREFER_HTTPS` to `1`, open a new terminal, and redo Step 4. |
| The `/agentic-qe:` commands don't show up | Restart Claude Code. Still missing? Type `/plugin` and check `agentic-qe` is listed and enabled. |

<details>
<summary>Optional: install a specific version</summary>

To stay on one release instead of always getting the latest, put `#` and
the release's tag name after the repo in the first Step 4 command:

```
/plugin marketplace add Cognify-Analytics/Agentic-QE#<tag>
```

</details>

## Run it locally

From the target repo (it must be a git repo):

```
/agentic-qe:test-pipeline                     # whole repo, report-only
/agentic-qe:test-pipeline src/pricing.py      # just one target
```

The pipeline writes its scratch files to `.claude-pipeline/` (added to
`.gitignore` for you) and its durable output to `.qa/`, which is meant to
be committed. At the end it lists exactly which files to commit.

### Filing issues and PRs from your machine

Add `--live` to file issues and open PRs the same way the GitHub Action
does:

```
/agentic-qe:test-pipeline --live
```

What you need first:

- The [GitHub CLI](https://cli.github.com), logged in (`gh auth login`)
  as someone with **write** access to the repo. A GitHub MCP server also
  works, and is tried first.
- Your current branch **pushed, with no unpushed commits.** In CI the PR
  base is always a branch that already exists on GitHub. Locally, an
  auto-fix branch cut from unpushed commits would carry them into the PR,
  so the run refuses instead.

Before generating any tests, the pipeline runs `scripts/gh_preflight.py`
to check all of this. If anything is missing it stops straight away and
says what to fix, rather than failing at the end of the run or quietly
switching to report-only. The result goes into `run.json` as a `local`
block, the local counterpart of CI's `ci` block. It pins the repo
(`--repo` on every `gh` call, like CI's `GH_REPO`) and picks the PR base:

| You're on | Fix PRs target |
|---|---|
| A pushed feature branch | That branch, so the fixes flow into your own PR, same as CI |
| The default branch | The default branch, through a PR. Nothing is ever pushed to it directly |

When triage finishes, it switches you back to the branch you started on.
A test file that was committed to an `auto-fix/...` branch now lives in
that PR and leaves your working tree. The summary names the PR and leaves
those files off your "please commit" list.

### Local vs CI at a glance

| | Local (`--live`) | GitHub Action (`live: true`) |
|---|---|---|
| Issues filed for suspected bugs | ✅ | ✅ |
| Auto-fix PR for SIMPLE test fixes | ✅ | ✅ |
| Bug-fix PRs (`fix_bugs`) | ✅ | ✅ |
| Issues/PRs assigned to CODEOWNERS | ✅ | ✅ (teams mentioned, not expanded — see below) |
| PR base | Your branch if pushed, else the default branch | The PR's own head branch |
| GitHub credentials | Your `gh` login | The workflow's `GITHUB_TOKEN` |
| `.qa/` committed | By you | By the workflow |
| Sticky summary comment on the PR | — | ✅ |
| Cost telemetry | — | ✅ |
| "No production source changed" assertion | — | ✅ (fails the job) |

### Who gets assigned

If the target repo has a `CODEOWNERS` file (in the root, `.github/` or
`docs/`), every issue and PR the pipeline opens is routed to the owners of
the code involved:

| Opened | Owners of | Assigned | Review requested |
|---|---|---|---|
| Issue for a suspected bug | The source module under the failing test | ✅ | — |
| Auto-fix PR (SIMPLE test fixes) | The source modules the fixed tests cover | ✅ | ✅ |
| Bug-fix PR (`fix_bugs`) | The source file(s) the fix changed | ✅ | ✅ |

Re-running on a failure that already has an open issue adds any missing
owners to that issue as assignees, instead of filing a duplicate.

GitHub only accepts some owners as assignees, so `scripts/resolve_owners.py`
checks each one first:

- **`@user` with access to the repo:** assigned, and asked to review PRs.
  You're never asked to review your own PR on a local run.
- **`@org/team`:** asked to review PRs as a team. An issue can't be
  assigned to a team, so its members are assigned instead, when the token
  can list them. A local run with your `gh` login usually can. In CI the
  workflow's `GITHUB_TOKEN` can't read org teams, so the team is
  @mentioned on the issue instead, which still notifies it.
- **Email addresses, and users without repo access:** @mentioned in the
  body, never assigned.

Owners are added in a separate step after the issue or PR is created. An
owner GitHub rejects therefore never stops the issue or PR from being
filed: the run records the error and carries on. GitHub caps assignees at
10, so direct owners come before team members. With no `CODEOWNERS`, or no
matching rule, nobody is assigned; the pipeline never guesses.
Report-only runs list the owners in the drafted issue and don't contact
GitHub.

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
runs.

Afterwards the workflow asserts no production source was touched, commits
`.qa/` onto the PR's head branch, posts a sticky PR comment with
`summary.md`, and uploads the scratch files as an artifact. SIMPLE test
fixes arrive as a separate auto-fix PR against the developer's own branch.
The pipeline never pushes to or merges into a default branch.

### Set it up in a target repo

1. In the target repo, add these secrets: `ANTHROPIC_API_KEY` (an
   Anthropic API key), and — while this repo is private —
   `AGENTIC_QE_READ_TOKEN` (a token with read access to it).
2. Copy [`templates/qa-caller-workflow.yml`](templates/qa-caller-workflow.yml)
   into the target repo as `.github/workflows/qa.yml`, and adjust
   `setup_script` to install that repo's dependencies and test framework.
   Set `plugin_ref` to the same ref you call the workflow at — the job
   warns if the two drift apart.
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

Draft PRs, PRs from forks, and PRs labelled `qa:skip` are skipped.

### `fix_bugs` — opt-in bug-fix PRs

Off by default, both locally (`--fix-bugs`) and in CI (`fix_bugs: true`).
When on, `/triage-tests` may, for a narrow set of COMPLEX failures backed by
a specific documented expectation (see `rules/error-classification.md`),
write an actual fix to production source, verify it against the full suite,
and open a **second PR** — separate from the routine test-fix PR — that
references the issue already filed for that failure (`Relates to #N`, never
auto-closing it) and is clearly marked as needing careful human review.

The pipeline still never merges anything; this only ever produces
something for a human to review and close themselves. It works
independently of `live` — without it, triage only computes and reports
what it would fix, which is a good way to gauge the blast radius before
turning it on for real. Make sure branch protection with required human
review is in place first — a bug-fix PR changes production code, not just
tests.

### ClickUp branch naming — opt-in

Some repos only allow branch names that carry a ClickUp task ID, such as
`feature/CU-86bbh0u96-common-rules-implementation`. The pipeline's own
branches (`auto-fix/triage-a1b2c3d` and so on) don't, so it can't push
them there. Turn this option on and the pipeline names its branches after
**the task ID of the branch it is running on**. It reuses that ID, so
nobody has to create a new ClickUp task.

#### Turning it on

In the target repo's `.github/workflows/qa.yml`:

```yaml
    with:
      clickup_branch_naming: true
```

For a local run, pass `--clickup-branches` instead
(`/agentic-qe:test-pipeline --live --clickup-branches`).

Leave it off if your repo has no naming rule. Nothing changes then.

#### Where the task ID comes from

You normally don't type it anywhere. The pipeline looks in two places, in
this order:

1. **The branch name.** It takes the first `CU-<letters and digits>` part,
   so `bug/CU-101010-cache-loading` gives `101010`. Lowercase `cu-` works
   too.
2. **The `clickup_task_id` box.** It's only checked when the branch name
   has no ID. The box only appears when you start a run by hand
   (**Actions → QA Pipeline → Run workflow**), and accepts `CU-86bbh0u96`
   or just `86bbh0u96`.

On pull requests the box doesn't exist, and the developer's branch already
carries the ID, so it is always automatic.

#### What happens in each case

**Option off.** The box is ignored. Branches get the default names, and
everything works as before.

**Option on, ID found.** Everything works as normal, only the branch names
change. A run on `bug/CU-101010-cache-loading` pushes:

| Branch for | Option off | Option on |
|---|---|---|
| Test fixes | `auto-fix/triage-a1b2c3d` | `auto-fix/CU-101010-triage-a1b2c3d` |
| Each bug fix (`fix_bugs`) | `auto-fix/bugfix-issue-9` | `auto-fix/CU-101010-bugfix-issue-9` |
| `.qa/` baseline (manual run on `main`) | `agentic-qe/qa-baseline-a1b2c3d` | `auto-fix/CU-101010-qa-baseline-a1b2c3d` |

**Option on, no ID found.** For example, a manual run on `main` with the
box left empty. Any branch the pipeline created would break the naming
rule, so it creates **no new branches**. The rest of the run still
happens:

| Part of the run | Happens? |
|---|---|
| Tests generated, run, and failures classified | ✅ Yes |
| GitHub issues filed for suspected bugs | ✅ Yes (an issue needs no branch) |
| Test fixes worked out and checked | ✅ Yes, but not committed or pushed |
| Test-fix PR and bug-fix PRs | ❌ Not opened. The run summary describes what they would contain |
| `.qa/` baseline branch and PR | ❌ Not pushed. The `.qa/` results are in the run's downloadable artifact |
| A warning on the job explaining why | ✅ Yes |

To get the branches and PRs, run it again by hand with the task ID in the
box. Locally there's no fallback: a `--live --clickup-branches` run on a
branch without an ID stops before it starts, and asks you to switch to a
branch named after its task.

#### Good to know

- **On pull requests this almost never comes up.** The developer's branch
  already follows the policy. The no-ID case is mostly the first manual
  run on `main`, so remember the box for that one.
- **If both have an ID, the branch name wins.** The box is only a
  fallback.
- **`.qa/` on a pull request is unaffected.** The workflow commits it onto
  the developer's own existing branch, which isn't a new branch, so the
  naming rule doesn't apply.
- All the naming logic lives in `scripts/branch_names.py`. To see what a
  branch name would produce, run
  `python scripts/branch_names.py --branch bug/CU-101010-cache-loading --sha a1b2c3d --clickup`.

## Where a run gets recorded

A run writes the same `.qa/` output whether it runs locally or in CI — what
differs is only how it persists.

**Locally**, `.qa/` lands in your working tree and the pipeline reminds you
to commit it. It never commits `.qa/` or your own branch on your behalf.
The only commits it makes are on its own `auto-fix/...` branches, and only
with `--live`.

**In CI**, the runner is ephemeral, so the workflow commits `.qa/` itself
in a dedicated "Record the run in `.qa/`" step:

| Trigger | Where `.qa/` lands |
|---|---|
| `pull_request` | Committed straight onto the PR's own head branch, so the record travels with the PR and reaches your default branch when you merge it |
| `workflow_dispatch` on the default branch | Pushed to `agentic-qe/qa-baseline-<sha>` (or its [ClickUp name](#clickup-branch-naming--opt-in)) with a PR opened — the pipeline never pushes to a default branch (PRD Section 9, Rule 5) |

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
those runs it skips work rather than doing it cheaply.

**What gets skipped, and when:**

| Situation | Effect |
|---|---|
| PR changes no source file (`strategy: triage-only`) | `/generate-tests` is never invoked — the orchestrator writes its completion record directly instead of forking a subagent that would load ~15k tokens of rules to do nothing |
| No doc/manifest/schema file changed, and no new tests were written | `/build-context` is never invoked — it would otherwise regenerate all four sections from the whole repo just to discover nothing changed |
| Test suite passes cleanly | `/triage-tests` reads only the totals, never the full output — the raw log is still saved for the artifact |

The first two depend on the PR diff the workflow computes, so they apply
in CI only. A local run always runs every stage.

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
strategy and per-stage outcomes too, locally and in CI. Join it to a
`telemetry.json` on `sha` to get the full picture — the cost figures can
only come from the CI side, since a run has no way to observe its own token
spend from inside.

**If you want to tune further:** the `model` input sets `--model` for the
whole pipeline. Measure before reaching for it — an Opus→Sonnet swap
observed here moved a run from $1.90 to $1.19, far less than the ~5x
price difference would suggest, which is exactly what tells you the run is
volume-bound rather than price-bound. Note also that `max_turns` is a
ceiling that stops a runaway run; lowering it does not make a normal run
cheaper.

## Project layout

- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — the plugin/marketplace manifests that make one-step install possible
- `skills/` — the four skills (`generate-tests`, `build-context`, `triage-tests`, `test-pipeline`)
- `rules/` — the single shared source of testing rules and conventions, read by the skills
- `templates/` — the GitHub issue and bug-fix PR templates, and the caller workflow to copy into a target repo
- `scripts/` — helper scripts the skills shell out to:
  - `parse_coverage.py` — turns a Cobertura `coverage.xml` into the coverage JSON `.qa/test-inventory.json` uses
  - `resolve_owners.py` — maps files to their CODEOWNERS owners, and to who GitHub will accept as assignee/reviewer
  - `gh_preflight.py` — checks GitHub access before a local `--live` run
  - `branch_names.py` — names every branch the pipeline pushes, including ClickUp task-ID naming
- `fixtures/` — a sample repo with known, documented bugs, used to grade `/triage-tests`
- `.github/workflows/qa-pipeline.yml` — the reusable GitHub Actions workflow

## Working on this repo itself

If you're developing the skills themselves (not just using them), point
Claude Code at your local checkout instead of installing from the
marketplace:

```
claude --plugin-dir .
```

Run `/reload-plugins` after editing a `SKILL.md` to pick up changes
without restarting.
