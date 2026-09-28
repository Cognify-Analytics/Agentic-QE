# Plan — Agentic QE as a GitHub Action (PR-triggered)

Companion to `PRD-qa-pipeline-v1.md`. This is the Phase 4 "GitHub Action"
deliverable.

**Verified against** `anthropics/claude-code-action@v1` `action.yml` on `main`,
September 2026.

---

## The design in one paragraph

Agentic-QE stays the plugin source. Each product repo gets a small caller
workflow that runs a **reusable workflow** hosted in Agentic-QE. On a PR, that
workflow checks out the plugin, installs the repo's dependencies, decides in
bash whether this is a first run or an incremental one, writes
`.claude-pipeline/run.json`, and makes **one** call to
`claude-code-action` running `/agentic-qe:test-pipeline`. The skill does the
rest exactly as it does locally. Afterwards the workflow asserts no production
source was touched, posts `summary.md` as a sticky PR comment, and uploads the
scratch files as artifacts. Test fixes and the updated `.qa/` folder arrive as
a PR against the developer's own branch.

---

## Decisions

| Question | Decision |
|---|---|
| Where the plugin lives | Agentic-QE, checked out into CI and loaded with `--plugin-dir`, pinned to a tag. |
| How aggressive | Full live: real issues, real auto-fix PR. Never merges. |
| What it targets | No `.qa/` → whole repo. `.qa/` present → only source files changed in the PR. |
| Auth | `ANTHROPIC_API_KEY` org secret. |
| Auto-fix PR base | The PR's own head branch, so the fix flows into the developer's PR. |
| Does the check ever go red? | Only on a pipeline error or a safety violation. **Never** for a COMPLEX finding — those are usually pre-existing bugs, and a red X for someone else's bug gets the workflow switched off. |
| Where `.qa/` gets committed | Onto the auto-fix branch, in the same PR. Never to `main`. |
| Trigger events | `opened`, `ready_for_review`, `workflow_dispatch`. Not `synchronize` — one run per PR, not one per push. |

This resolves PRD open questions Q5, Q6 and Q7.

---

## Skill changes needed

Five edits in Agentic-QE. Each should be its own commit.

**1. `test-pipeline` — accept a CI-written `run.json`.**
Today the skill writes `run.json` itself in "Before starting". Change it to: if
`.claude-pipeline/run.json` already exists and its `mode` is `"ci"`, read it and
do not overwrite. Everything downstream is unchanged. Also delete the L20-22
disclaimer that says CI is out of scope.

**2. `test-pipeline` — don't edit `.gitignore` in CI.**
Step 5 appends `.claude-pipeline/` to the target repo's `.gitignore`, which
dirties a tracked file on every run. When `mode` is `"ci"`, skip it — the
workflow writes the same line to `.git/info/exclude` instead, which is local to
the checkout and untracked.

**3. `generate-tests` — never ask a question in CI.**
Three places stall a headless run until the job times out:
- Step 10 skips the approval prompt only when `mode` is exactly `"pipeline"` →
  accept `"ci"` too.
- Step 3 rule 3 ("can't tell where tests go? ask the user") → in CI, write
  `01-tests.json` with `status: "failed"` and a reason, and stop.
- "Target not found" in Troubleshooting → same.

Also: if `run.json` has a non-empty `ci.targets` array, test exactly those paths
and skip the Step 5 top-20 ranking. Empty or absent means whole-repo (bootstrap).

**4. `triage-tests` — never ask, and know where to aim the PR.**
- Step 2 ("test command unknown? ask the user") → in CI, write `03-triage.json`
  with `status: "failed"` and stop.
- Step 8: base the auto-fix PR on `run.json`'s `ci.pr_base_branch`, not the
  default branch. If that field is missing, fall back to report-only rather than
  guessing a base.
- Step 8: also commit `.qa/context.md`, `.qa/test-inventory.json` and
  `.qa/runs/<date>-<sha>.json` onto that branch. Without this, `.qa/` never
  reaches the repo and every future PR bootstraps from scratch at full cost.
- Step 7: put a stable fingerprint (test name + file) in the issue title and
  search on it before opening a new one, so a re-run comments instead of
  duplicating.

**5. `build-context` — no changes.** It has no `Bash` and no `AskUserQuestion`,
and already degrades gracefully when the inventory is missing.

### `run.json` in CI

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

`strategy` is `bootstrap` | `incremental` | `triage-only`.

---

## The workflow

`.github/workflows/qa-pipeline.yml` in Agentic-QE, as `on: workflow_call`.

### Triggers and guards

```yaml
on:
  workflow_call:
    inputs:
      setup_script: { required: true, type: string }
      live:         { required: false, type: boolean, default: false }

permissions:
  contents: write        # create the auto-fix branch
  pull-requests: write   # open the auto-fix PR, post the comment
  issues: write          # file COMPLEX issues

concurrency:
  group: qa-pipeline-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

Job guard — all three conditions matter:

```yaml
if: >
  github.event.pull_request.head.repo.full_name == github.repository &&
  github.event.pull_request.draft == false &&
  !contains(github.event.pull_request.labels.*.name, 'qa:skip')
```

The first condition is not optional. A PR from a fork gets no secrets, so
`ANTHROPIC_API_KEY` would be absent anyway — and the obvious workaround,
`pull_request_target`, would run the PR's test suite (arbitrary code) with your
API key and a write token. Fork PRs are simply out of scope.

`timeout-minutes: 60`.

### Steps

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0                                    # the diff needs base..head
    ref: ${{ github.event.pull_request.head.sha }}

- name: Check out the Agentic QE plugin
  uses: actions/checkout@v4
  with:
    repository: Cognify-Analytics/Agentic-QE
    ref: v0.2.0                                       # pin — never float on main
    path: .agentic-qe
    token: ${{ secrets.AGENTIC_QE_READ_TOKEN }}

- name: Keep scratch out of the diff
  run: printf '%s\n' '.claude-pipeline/' '.agentic-qe/' >> .git/info/exclude

- uses: actions/setup-python@v5                       # parse_coverage.py and
  with: { python-version: '3.12' }                    # resolve_owners.py need it
                                                      # even in a non-Python repo
- name: Install target repo dependencies
  run: ${{ inputs.setup_script }}

- name: Configure git identity
  run: |
    git config user.name  'agentic-qe[bot]'
    git config user.email 'agentic-qe[bot]@users.noreply.github.com'
```

### Deciding what to run

Pure bash — no model discretion:

```yaml
- name: Decide strategy and write run.json
  id: plan
  env:
    BASE: ${{ github.event.pull_request.base.ref }}
  run: |
    set -euo pipefail
    mkdir -p .claude-pipeline

    if [ -f .qa/test-inventory.json ] && [ -f .qa/context.md ] \
       && jq -e '.modules' .qa/test-inventory.json >/dev/null 2>&1; then
      STRATEGY=incremental
    else
      STRATEGY=bootstrap
    fi

    TARGETS='[]'
    if [ "$STRATEGY" = incremental ]; then
      git fetch --no-tags origin "$BASE"
      CHANGED=$(git diff --name-only --diff-filter=d "origin/$BASE...HEAD" \
        | grep -Ev '(^|/)(tests?|spec|__tests__)/' \
        | grep -E '\.(py|js|jsx|ts|tsx|java|kt|go|rb|cs|rs|php)$' || true)
      if [ -z "$CHANGED" ]; then
        STRATEGY=triage-only
      else
        TARGETS=$(printf '%s\n' "$CHANGED" | jq -R . | jq -sc .)
      fi
    fi

    jq -n \
      --arg sha "$(git rev-parse --short HEAD)" \
      --arg branch "${{ github.head_ref }}" \
      --arg ts "$(date -u +%FT%TZ)" \
      --arg strategy "$STRATEGY" \
      --argjson targets "$TARGETS" \
      --argjson pr "${{ github.event.pull_request.number || 'null' }}" \
      --argjson live "${{ inputs.live && 'true' || 'false' }}" \
      --arg run_url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" '
      { sha:$sha, branch:$branch, timestamp:$ts, mode:"ci", live:$live,
        ci: { pr_number:$pr, pr_base_branch:$branch, run_url:$run_url,
              strategy:$strategy, targets:$targets } }' > .claude-pipeline/run.json

    cat .claude-pipeline/run.json
```

What that produces:

| `.qa/` baseline | PR touches source | Strategy | Effect |
|---|---|---|---|
| absent | — | `bootstrap` | Whole repo, skill's own top-20 ranking |
| present | yes | `incremental` | Only the changed files |
| present | no | `triage-only` | `generate-tests` writes nothing; suite still runs |

`triage-only` will be a large share of real PRs, and it costs almost nothing.

### The one Claude call

```yaml
- name: Run the QA pipeline
  uses: anthropics/claude-code-action@v1
  with:
    anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
    prompt: '/agentic-qe:test-pipeline'
    track_progress: false
    settings: |
      { "env": { "GH_TOKEN": "${{ secrets.GITHUB_TOKEN }}",
                 "GH_REPO":  "${{ github.repository }}" } }
    claude_args: |
      --plugin-dir ./.agentic-qe
      --max-turns 150
      --allowedTools "Read,Write,Edit,Glob,Grep,Bash"
```

Three things to notice:

- **No arguments in the prompt.** Mode, live flag and target list all travel via
  `run.json`. Nothing about the PR — title, body, comments — is ever
  interpolated into the prompt, which keeps the prompt-injection surface at zero.
- **`AskUserQuestion` is absent from the allowlist** on purpose, as a hard
  backstop behind skill change 3.
- **`settings.env` is how `GH_TOKEN` reaches the Bash tool** — `triage-tests`
  falls back to the `gh` CLI, and `gh` is on the runner but unauthenticated
  without this.

`--max-turns 150` is a starting guess covering the orchestrator plus three
forked stages. Log the actual turn count on the first ten runs and tighten it.

### The safety check

The single most valuable step in the workflow. PRD §9 rule 1 says never change
production source; this is what makes that provable rather than prompted.

```yaml
- name: Assert no production source was changed
  if: always()
  run: |
    set -euo pipefail
    LOC=$(jq -r '.test_location // "tests/"' .claude-pipeline/01-tests.json 2>/dev/null || echo tests/)
    BAD=$(git status --porcelain | awk '{print $2}' \
          | grep -Ev "^(${LOC}|\.qa/|\.claude-pipeline/)" || true)
    if [ -n "$BAD" ]; then
      echo "::error::pipeline modified files outside the test location:"
      echo "$BAD"
      exit 1
    fi
```

### Report and artifacts

A deterministic step, not a model instruction — it survives a failed run:

```yaml
- name: Post summary comment
  if: always() && github.event_name == 'pull_request'
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    PR: ${{ github.event.pull_request.number }}
  run: |
    { echo '<!-- agentic-qe-summary -->'
      cat .claude-pipeline/summary.md 2>/dev/null || echo 'QA pipeline did not complete — see the run log.'
      echo; echo "_[run](${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }})_"
    } > body.md
    ID=$(gh api "repos/${{ github.repository }}/issues/$PR/comments" \
         --jq '.[] | select(.body | contains("agentic-qe-summary")) | .id' | head -1)
    if [ -n "$ID" ]; then
      gh api -X PATCH "repos/${{ github.repository }}/issues/comments/$ID" -F body=@body.md
    else
      gh pr comment "$PR" --body-file body.md
    fi

- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: qa-pipeline-${{ github.run_id }}
    path: |
      .claude-pipeline/
      .qa/
    retention-days: 14
```

Keep `raw-test-output.txt` in the artifact — it's what makes a disputed
classification arguable after the fact.

### Caller workflow, in each product repo

```yaml
# .github/workflows/qa.yml
name: QA Pipeline
on:
  pull_request:
    types: [opened, ready_for_review]
    paths-ignore: ['**/*.md', 'docs/**', '.github/**']
  workflow_dispatch:

jobs:
  qa:
    uses: Cognify-Analytics/Agentic-QE/.github/workflows/qa-pipeline.yml@v0.2.0
    secrets: inherit
    with:
      live: true
      setup_script: |
        python -m pip install -U pip
        pip install -r requirements.txt
        pip install pytest pytest-cov
```

---

## How `.qa/` survives

This is the part that makes the adaptive strategy work, so it's worth being
explicit. `triage-tests` in live mode creates `auto-fix/triage-<sha>`, commits
the SIMPLE test fixes, and (after skill change 4) the `.qa/` files too, then
opens a PR **against the developer's branch**. The developer merges it into
their own PR; `.qa/` reaches `main` through their normal merge. The pipeline
never pushes to `main` and never merges anything, so PRD §9 rules 3-6 hold.

If a run generated tests but found no failures, `triage-tests` never creates a
branch and the output would be silently discarded — so add a fallback step that
creates the branch, commits `.qa/` plus the files listed in `01-tests.json`'s
`files_created`/`files_modified`, and opens the PR with
`gh pr create --base "${{ github.head_ref }}"`.

A PR opened with `GITHUB_TOKEN` does not trigger other workflows, so the
auto-fix PR won't re-run this pipeline. That's the behavior you want — no loop
guard needed.

---

## Build order

### Phase 1 — plumbing, manual, report-only

1. **Smoke-test the plugin path first, on its own.** A throwaway workflow with
   one `claude-code-action` step, `--plugin-dir ./.agentic-qe`, and a prompt
   asking it to run `/agentic-qe:build-context` and report what
   `${CLAUDE_PLUGIN_ROOT}` resolved to. Every skill depends on that variable
   resolving to the checkout — if it doesn't, nothing else matters. Fix this
   before building anything on top of it.
2. Make skill changes 1-4. Tag Agentic-QE `v0.2.0`.
3. Write `qa-pipeline.yml` with all the steps above, `live: false`.
4. Add the caller in **one** target repo, `workflow_dispatch` only.
5. Run it. Confirm `01-tests.json`, `context.md`, `03-triage.json`,
   `summary.md` and `.qa/runs/*.json` all land in the artifact.
6. **Prove the gates.** Temporarily make `generate-tests` write
   `{"status":"failed","reason":"deliberate"}` and confirm the pipeline stops
   before stage 2. This is the PRD's Phase 4 finish criterion.
7. **Prove the safety check.** Have a run touch a source file on purpose and
   confirm the job goes red.

**Done when** a manual run produces all five files, a broken stage 1 halts it,
and the safety assertion demonstrably fires.

### Phase 2 — PR-triggered, still report-only

8. Add the `pull_request` trigger and guards.
9. Verify all three strategies on real PRs: one touching source, one touching
   only docs, and one in a repo with no `.qa/` yet.
10. Confirm the sticky comment updates rather than stacking.

**Done when** three PRs of different shapes each get a correct comment, and
nothing is filed or pushed.

### Phase 3 — live

11. Turn on branch protection on `main` in the target repo **first** — require
    a PR and at least one human approval. `pull-requests: write` technically
    permits merging, so don't rely on the model's restraint alone.
12. Set `live: true`. Verify the auto-fix PR: base is the PR's head branch, it
    contains only test files and `.qa/`, and it is never merged.
13. Verify issue dedupe — run twice on the same PR and confirm the second run
    comments on the existing issue.
14. Merge one auto-fix PR end to end, then open a **new** PR in that repo and
    confirm it runs `incremental`, not `bootstrap`.

Step 14 is the proof the whole persistence design works. Until it passes,
assume it doesn't.

---

## Files

In Agentic-QE:

```
.github/workflows/qa-pipeline.yml   new — reusable workflow
skills/test-pipeline/SKILL.md       edit — changes 1, 2
skills/generate-tests/SKILL.md      edit — change 3
skills/triage-tests/SKILL.md        edit — change 4
README.md                           edit — document the CI path
```

In each target repo: `.github/workflows/qa.yml`, plus `.qa/` created by the
first run.

Secrets: `ANTHROPIC_API_KEY` (org-level) and `AGENTIC_QE_READ_TOKEN` while
Agentic-QE is private. Branch protection on `main` before Phase 3.

---

## Three things that will bite

**`--max-turns` too low.** A truncated stage looks like a failure. Start at 150,
watch the real numbers, tighten. Stage-gate failures will catch truncation
rather than passing bad output downstream.

**Bootstrap PRs are big.** A first run on an established repo generates up to 20
modules' worth of tests. That's a real review burden. If it becomes a problem,
run bootstrap once via `workflow_dispatch`, merge it, and let every PR after
that be incremental.

**Flaky tests land as COMPLEX.** They won't match any SIMPLE pattern, so they'll
be filed as suspected bugs. That's the correct conservative behavior, but it's
noisy on a flaky suite — worth knowing before you point this at one.

---

## Addendum — optional bug-fix mode (`fix_bugs`)

Added after the initial GitHub Action shipped, at explicit request: a new
`fix_bugs` boolean input on the reusable workflow (default `false`,
independent of `live`), threaded into `run.json` the same way `live` is.
When on, `/triage-tests` may write a verified fix to production source for
a narrow, capped set of COMPLEX bugs (see PRD Section 9.1) and open a
**second** PR — separate from the SIMPLE-fix PR this plan already
describes — that references the issue already filed for that failure
(`Relates to #N`, never auto-closing it).

No changes to the job's `permissions:` block were needed — `contents:
write`, `pull-requests: write`, and `issues: write` already cover the
second branch/PR and the issue cross-comment.

This raises the bar on the Phase 3 guidance above: "require a PR and at
least one human approval" changes from *strongly recommended* to a
precondition worth stating outright before anyone flips `fix_bugs: true`
in the caller workflow — see the reusable workflow's `fix_bugs` input
description and README, "Set it up in a target repo," step 5.
