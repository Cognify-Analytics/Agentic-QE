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
| `/agentic-qe:build-context` | Build/update `.qa/context.md`, a living project overview, and `.qa/github-action-qa-pipeline-template.yml`, the CI workflow with this repo's setup already filled in |
| `/agentic-qe:triage-tests [--live] [--fix-bugs]` | Run the suite, classify each failure as a bad test or a real bug, fix what's safe, file issues for the rest |
| `/agentic-qe:test-pipeline [--live] [--fix-bugs] [file or folder]` | Run all three in sequence, end to end |

| Flag | Effect |
|---|---|
| *(none)* | Report-only. Every issue and PR is drafted in `.claude-pipeline/03-triage.json`, and nothing reaches GitHub |
| `--live` | Actually file issues and open PRs (see [Filing issues and PRs from your machine](#filing-issues-and-prs-from-your-machine)) |
| `--clickup-branches` | Opt-in. Names every branch the pipeline pushes after your branch's ClickUp task ID (see [ClickUp branch naming](#clickup-branch-naming--opt-in)) |
| `--fix-bugs` | Opt-in. Lets triage attempt a narrow, verified fix to production source for some real bugs (see [`fix_bugs`](#fix_bugs--opt-in-bug-fix-prs)). Without `--live`, it only reports what it would change |

## Supported languages

The pipeline works out a repo's language and test setup from its manifest
files, and never assumes one. Every language gets the shared rules in
`rules/general/`. Four languages also have their own rules folder:

| Language | Rules | Test frameworks | Framework-specific rules | Coverage read from |
|---|---|---|---|---|
| Python | `rules/lang/python/` | pytest | — | pytest-cov (Cobertura) |
| JavaScript / TypeScript | `rules/lang/javascript/` | Jest, Vitest, `node:test` | React, Next.js (App and Pages Router), Node backends (Express, Fastify, NestJS, Koa, Hono) | Cobertura or LCOV (Jest, Vitest, c8, `node --test`) |
| Java | `rules/lang/jvm/` + `rules/lang/java/` | JUnit 5 (JUnit 4 when that's all there is), AssertJ, Mockito | Spring Boot | JaCoCo (Maven, Gradle) |
| Kotlin | `rules/lang/jvm/` + `rules/lang/kotlin/` | JUnit 5, Kotest, MockK (or Mockito via mockito-kotlin), coroutines | Spring Boot | JaCoCo or Kover |

Go, C#, Rust, Ruby, PHP, Elixir, Scala and Swift are detected and get
the general rules, their default test location and their build commands,
but no language-specific rules yet.

The pipeline never edits a manifest or build file. Whatever the tests need
(Jest or Vitest, `@testing-library/*`, `junit-jupiter`, Mockito or MockK,
a coverage provider) must already be in the repo. If something is missing,
the run says exactly what, and skips the modules that need it.

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
| Step-by-step timeline of what the agent did | — | ✅ |
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

Afterwards the workflow asserts no production source was touched (see
[The safety check](#the-safety-check)), commits `.qa/` onto the PR's head
branch, posts a sticky PR comment with `summary.md`, and uploads the
scratch files as an artifact. SIMPLE test fixes arrive as a separate
auto-fix PR against the developer's own branch. The pipeline never pushes
to or merges into a default branch.

### The safety check

After Claude finishes, the step **"Assert no production source was
changed"** runs `scripts/check_test_only_changes.py`. It sorts every
changed file into one of these groups:

| Group | Examples | Result |
|---|---|---|
| Pipeline output | `.qa/`, `.claude-pipeline/` | ✅ Allowed |
| Tests | Anything in a `tests/`, `test/`, `spec/`, `__tests__/`, `test-utils/` or `src/test/` folder, or a Gradle test source set (`src/testFixtures/`, `src/jvmTest/`); files named `test_x.py`, `x.test.ts`, `x.spec.js`, `x_test.go`, `FooTest.java`, `FooTest.kt`, `conftest.py`, `test-utils.tsx` | ✅ Allowed, including tests that sit next to the code (`src/lib/format.test.ts`) |
| Test-run by-products | `coverage.xml`, `.coverage`, `coverage/`, `htmlcov/`, `__pycache__/`, `.venv/`, `target/`, `build/`, `.gradle/`, `.next/`, `*.tsbuildinfo` | ✅ Ignored. Only counts for new, untracked files, and they're never committed |
| Already changed before Claude started | A lock file rewritten by `setup_script` | ✅ Not judged. A snapshot is taken just before Claude runs |
| Anything else | Production source, config, lock files | ❌ The job fails |

When it fails, the error annotation lists every file that caused it.
Because the check fails, `.qa/` isn't recorded for that run, so fix the
cause and run it again.

Tests are recognised by their folder or file name, never by what the run
says it wrote: a check that trusted the model's own report wouldn't check
anything. If a repo keeps tests somewhere unusual, a genuine test can be
flagged. The patterns are at the top of the script.

### Set it up in a target repo

Everything below is done in your web browser on github.com, and you only
do it once per repo. It takes about 15 minutes.

The **target repo** is the repo you want the pipeline to test, not this
one.

**What you need first**

- **Admin access to the target repo.** You'll know you have it if you can
  see a **Settings** tab at the top of the repo's page. If you can't, ask
  whoever manages that repo.
- **A login for the Anthropic Console** (<https://console.anthropic.com>),
  which is where the API key comes from. Ask your team lead if you don't
  have one.
- **A developer on the target repo** who can spare 5 minutes for step 4.

#### Step 1 — Allow other repos to use this pipeline (once per org)

Skip this if someone has already done it. If unsure, ask, or just do it
again; it does no harm. It needs admin access to **Agentic-QE** (this
repo), not the target repo.

1. Open <https://github.com/Cognify-Analytics/Agentic-QE>.
2. Click **Settings → Actions → General**.
3. Scroll down to **Access**.
4. Choose **Accessible from repositories in the 'Cognify-Analytics'
   organization**.
5. Click **Save**.

#### Step 2 — Get an Anthropic API key

This is what lets the pipeline use Claude. Usage is billed to your
organization's Anthropic account.

1. Go to <https://console.anthropic.com> and log in.
2. Open **API Keys** and click **Create Key**.
3. Name it after the target repo, e.g. `agentic-qe-orders-service`.
4. **Copy the key now and paste it somewhere safe for a few minutes.**
   It's shown only once.

#### Step 3 — Create a GitHub token that can read this repo

The pipeline needs to download Agentic-QE, which is private, so it needs a
token that is allowed to read it.

1. On GitHub, click your profile picture (top right) → **Settings**.
2. In the left menu, scroll to the bottom: **Developer settings →
   Personal access tokens → Fine-grained tokens**.
3. Click **Generate new token** and fill in:
   - **Token name:** `agentic-qe-read`
   - **Expiration:** the longest your org allows. Put a reminder in your
     calendar, because the pipeline stops working when the token expires.
   - **Resource owner:** **Cognify-Analytics**
   - **Repository access:** **Only select repositories** → pick
     **Agentic-QE**
   - **Permissions → Repository permissions → Contents:** **Read-only**
4. Click **Generate token**, then **copy it straight away**. Like the API
   key, it's shown only once.

If GitHub says the token is "pending approval", an org admin has to
approve it before it works.

#### Step 4 — Save both as secrets in the target repo

Secrets are GitHub's safe place for passwords. Once saved, nobody can read
them back, not even you.

1. Open the **target repo** on GitHub.
2. Click **Settings → Secrets and variables → Actions**.
3. Click **New repository secret** and add the first one:
   - **Name:** `ANTHROPIC_API_KEY`
   - **Secret:** the key from step 2
4. Click **Add secret**. Then click **New repository secret** again for the
   second one:
   - **Name:** `AGENTIC_QE_READ_TOKEN`
   - **Secret:** the token from step 3
5. Click **Add secret**. Both names should now be listed.

The names must be typed **exactly** as shown, in capitals, with
underscores. Then delete the copies you pasted somewhere in steps 2 and 3.

#### Step 5 — Add the pipeline file to the target repo

1. **If the target repo has a `.qa/github-action-qa-pipeline-template.yml`**
   (`/agentic-qe:build-context` writes it, so it's there after any local
   or CI run), copy that file. It's the same workflow with the repo's setup
   already worked out: one install block per stack (backend, frontend, …)
   and the right Node/Java/Python versions, each line commented with the
   file it came from. Otherwise open
   [`templates/qa-caller-workflow.yml`](templates/qa-caller-workflow.yml)
   in this repo and copy all of its contents. The **Copy raw file** button
   at the top right of the file does this in one click.
2. In the target repo, click **Add file → Create new file**.
3. In the file name box, type exactly `.github/workflows/qa.yml`. The
   slashes create the folders for you.
4. Paste the contents.
5. **Ask a developer on that repo to check the `setup_script` part.** It's
   the list of commands that install the repo's software, it's different
   for every repo, and getting it wrong is the most common reason a first
   run fails. With the generated template they only need to review it,
   and fix any line that says "replace this line" (a stack it couldn't
   work out). With the generic template they write it themselves, and for
   a JavaScript/TypeScript repo also uncomment `node_version`, for
   Java/Kotlin `java_version`, set to the version the project builds with.
   Leave everything else as it is. In particular, keep `live: false` for
   now, so the pipeline only reports and doesn't file anything yet.
   `fix_bugs`, `model` and the other options in STEP 2 can be set later in
   your copy, whenever you want them.
6. Click **Commit changes**. If GitHub asks, choose to create a new branch
   and open a pull request, then get it approved and merged as usual.

#### Step 6 — Protect the main branch

The pipeline can open pull requests. This step makes sure a person always
has to approve one before it's merged, so nothing the pipeline writes
reaches `main` unseen.

1. In the target repo, click **Settings → Branches**.
2. Click **Add classic branch protection rule**.
3. **Branch name pattern:** `main` (or whatever the repo's main branch is
   called).
4. Tick **Require a pull request before merging**, then tick **Require
   approvals** underneath it and leave the number at **1**.
5. Click **Create** at the bottom.

If the repo already has a rule for `main` that requires at least one
approval, you're already covered.

#### Step 7 — Run it for the first time

The first run tests the whole repo, so start it on purpose rather than
letting it happen on someone's first pull request.

1. In the target repo, click the **Actions** tab.
2. In the left list, click **QA Pipeline**.
3. Click **Run workflow** (on the right), leave the branch as `main`, and
   click the green **Run workflow** button. If your repo uses
   [ClickUp branch naming](#clickup-branch-naming--opt-in), type a
   ClickUp task ID in the box first.
4. Wait for it to finish. Large repos can take up to an hour. A green tick
   means it worked.
5. It opens a pull request named **"Agentic QE: record run …"**. Merge it.
   That saves the results, so later runs only test what changed.

From now on it runs by itself when a pull request is opened or marked
ready for review. Pushing more commits to an open pull request doesn't
start it again. Draft pull requests, pull requests from forks, pull
requests labelled `qa:skip`, and pull requests that only touch docs or
`.github/` are skipped. See [When it runs, and on which
branch](#when-it-runs-and-on-which-branch) for the full rules.

#### Step 8 — Later: let it file issues and PRs

After watching a few runs and being happy with what it reports, change
`live: false` to `live: true` in `.github/workflows/qa.yml`. From then on
it files real GitHub issues and opens real pull requests.

### When it runs, and on which branch

Two workflow files are involved, and they do different jobs:

| File | Lives in | Decides |
|---|---|---|
| `.github/workflows/qa.yml` (copied from [`templates/qa-caller-workflow.yml`](templates/qa-caller-workflow.yml)) | The target repo | **When** to run, plus that repo's settings (`setup_script`, `live`, `clickup_branch_naming`, …) |
| `.github/workflows/qa-pipeline.yml` | This repo | **What** happens. It never runs by itself, only when a `qa.yml` calls it |

#### What starts a run

The caller only listens to these events:

```yaml
on:
  pull_request:
    types: [opened, ready_for_review]
    paths-ignore: ['**/*.md', 'docs/**', '.github/**']
  workflow_dispatch:
```

| You do this | Runs? |
|---|---|
| Create a branch and push it, without opening a PR | ❌ No. A push isn't a trigger |
| Open a pull request | ✅ Yes. It doesn't matter whether the branch is new or old |
| Open a **draft** pull request | ❌ Skipped |
| Click **Ready for review** on a draft | ✅ Yes |
| **Push more commits to an open pull request** | ❌ **No** |
| Close and reopen a pull request | ❌ No |
| Open a pull request that **only** changes `*.md`, `docs/` or `.github/` files | ❌ No, and no check appears on the PR at all |
| Open a pull request from a fork, or one labelled `qa:skip` | ❌ Skipped |
| **Actions → QA Pipeline → Run workflow** | ✅ Yes, on the branch you pick |

To test new commits on a pull request that is already open, either click
**Run workflow** on its branch, or click **Convert to draft** and then
**Ready for review** again. **Re-run jobs** on an old run doesn't work for
this, because it re-tests the commit that run used.

**Why did another check run but not QA?** Other workflows in the repo have
their own triggers. For example, a branch-name check that listens to
`opened, synchronize, reopened, edited` with no path filter runs on every
PR. QA doesn't run when every changed file matches `paths-ignore`. A PR
that only adds `.github/CODEOWNERS` and a workflow file shows the
branch-name check and nothing from QA. That's expected, because there's
no code to test. This includes the PR that adds `qa.yml` itself.

#### Which branch is used for what

In a pull request, **head** is the branch being merged in and **base** is
the branch it merges into. For example, take a PR from
`feature/CU-86bbh0u96-common-rules-implementation` (head) into
`feature/CU-86bbea67d-branch-naming` (base):

| Question | Answer | In the example |
|---|---|---|
| Whose code is tested? | **Head.** The workflow checks out the PR's head commit | `feature/CU-86bbh0u96-…` |
| What is the base used for? | Only to work out what changed (`git diff base...head`), which decides `incremental` vs `triage-only` | `feature/CU-86bbea67d-…` |
| Whose `qa.yml` is used? | GitHub reads it from the PR's merge commit (base and head combined). That's head's version if the PR edits `qa.yml`, otherwise base's. If neither branch has it, nothing runs | Base's, since the PR doesn't change it |
| Which pipeline version runs? | **Neither branch's.** It's this repo, at the ref in `qa.yml`'s `uses:` and `plugin_ref` | Whatever `uses:` names |
| Whose ClickUp task ID goes into new branch names? | **Head's** | `CU-86bbh0u96` |
| Where do auto-fix PRs point? | **Into the head branch**, never the base or the default branch | `auto-fix/CU-86bbh0u96-triage-<sha>` → `feature/CU-86bbh0u96-…` |
| Where is `.qa/` committed? | Straight onto the head branch. It reaches the base when the PR is merged | `feature/CU-86bbh0u96-…` |

So the chain looks like this:

```
auto-fix/CU-86bbh0u96-triage-<sha> ──PR──► feature/CU-86bbh0u96-… ──your PR──► feature/CU-86bbea67d-…
```

The workflow's own commits never start another run. Pushes made with the
workflow's `GITHUB_TOKEN` don't trigger workflows, and new commits on a PR
aren't a trigger anyway.

#### What a run decides to do

Before Claude starts, the workflow picks a strategy:

| Strategy | When |
|---|---|
| `bootstrap` | The head branch has no usable `.qa/` baseline. The whole repo is tested |
| `incremental` | There's a baseline, and the PR changes source files (outside test folders). Only those files are targeted |
| `triage-only` | There's a baseline, but no source files changed. Nothing new is generated; existing tests are run and triaged |

A branch only has the baseline if it was created, or rebased, after the
"Agentic QE: record run …" PR was merged.

A **manual run** has no base to compare against. With no baseline it
bootstraps, which is what you want for the first run (Step 7). With a
baseline it always comes out as `triage-only`, so it won't write tests for
new code. Open a PR for that.

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
- `/triage-tests` leaves the run on its own `auto-fix/...` branch. Before
  committing, the step switches back to the commit the run started from,
  so fix commits only ever reach the developer's branch through the fix PR.

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

## Seeing what the agent did

The job log shows the run as raw JSON, one blob per message, which is no
way to follow it. Under the cost table, the job summary also has a
section called **"Agentic QE — what the agent did"**:

- **How the run ended**: finished, or stopped at the turn limit, with
  turns and wall-clock time.
- **Each stage's outcome**: ran, skipped (and why), or not reached, with
  its time, step count, and how many of its steps were blocked or failed.
- **Skipped, and why**: stages the pipeline skipped, modules
  `/generate-tests` wrote no tests for, tests it discarded, and fixes
  `/triage-tests` gave up on.
- **Decisions**: the tests written, the tests kept failing on purpose as
  possible bugs, how each failure was classified and why, and the fixes
  made.
- **Blocked or failed actions**: tool calls that were denied or errored.
  These are often harmless, because the agent tries something, sees it
  fail, and adapts. They are still the first place to look when a run
  goes wrong.
- **Step by step**: one collapsed timeline per stage, showing every file
  read, command run, and file written, with timestamps. Between the
  steps is the agent's own commentary on what it's doing and why.

The full version, with untruncated commentary, command output, and each
stage's closing report, is `trace.md` in the `qa-pipeline-<run_id>`
artifact, next to the raw `execution-log.json` it is built from.
`scripts/render_trace.py` builds both versions. It also renders a local
headless run:

```
claude -p '/agentic-qe:test-pipeline' --output-format stream-json --verbose > run.jsonl
python scripts/render_trace.py run.jsonl --out trace.md
```

## Project layout

- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` — the plugin/marketplace manifests that make one-step install possible
- `skills/` — the four skills (`generate-tests`, `build-context`, `triage-tests`, `test-pipeline`)
- `rules/` — the single shared source of testing rules and conventions, read by the skills:
  `general/` for every language, `lang/<language>/` per language (with `frameworks/` for React, Next.js, Node backends and Spring Boot), `error-classification.md` for triage, `context-file-template.md` and `qa-workflow-template.md` for the two files `/build-context` writes
- `templates/` — the GitHub issue and bug-fix PR templates, and the generic caller workflow to copy into a target repo (`/build-context` also writes a copy tuned to the repo, in `.qa/`)
- `scripts/` — helper scripts the skills shell out to:
  - `parse_coverage.py` — turns Cobertura, JaCoCo or LCOV coverage reports (one, or one per module) into the coverage JSON `.qa/test-inventory.json` uses
  - `resolve_owners.py` — maps files to their CODEOWNERS owners, and to who GitHub will accept as assignee/reviewer
  - `gh_preflight.py` — checks GitHub access before a local `--live` run
  - `branch_names.py` — names every branch the pipeline pushes, including ClickUp task-ID naming
  - `render_trace.py` — turns a run's execution log into the readable "what the agent did" timeline
  - `check_test_only_changes.py` — the CI safety check that fails a run which changed anything but tests (see [The safety check](#the-safety-check))
- `fixtures/` — a sample (Python) repo with known, documented bugs, used to grade `/triage-tests`
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
