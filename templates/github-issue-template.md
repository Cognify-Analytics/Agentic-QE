<!--
Template for issues /triage-tests files for COMPLEX/AMBIGUOUS failures.
Fill every {placeholder}. Omit the "Owners" line entirely if
scripts/resolve_owners.py returned "owners": [] rather than leaving a
placeholder or guessing one. List every entry in "owners" -- the ones it
could assign are also set as assignees (triage-tests, "Assigning
CODEOWNERS"); naming them all here is what still notifies the
"mention_only" ones (emails, teams, people without repo access).

Every issue gets the `agentic-qe` label and keeps the marker comment
below exactly as shaped (valid JSON, one line). /follow-up-issues reads
both to act on maintainers' replies; an issue without them is never
followed up. Fill the marker's fields from the same values as the body.
"classification" is the error-classification row that decided COMPLEX
(e.g. "behaviour contradicts docs", "timing or race condition").
-->
Title: [QA Pipeline] {short description of the suspected defect}
Labels: agentic-qe

<!-- agentic-qe:issue {"fingerprint": "{test_name} ({test_file})", "test": "{test_name}", "file": "{test_file}", "source": "{source_file}", "stack": {"stack name" or null}, "classification": "{classification row}", "generated_by_qa": {true|false}, "origin_branch": "{branch the run was on}", "origin_sha": "{git_sha}"} -->

**Failing test:** {test_name}
**File:** {test_file}
**Detected at:** {git_sha}

**What happened**
{one or two lines: what was expected vs what actually happened, plus the
raw assertion/error line}

**Why we think this is a real bug, not a bad test**
{the specific evidence: a quote or reference from .qa/context.md, a docstring,
or an adjacent doc, contrasted with what the code actually does at
{file}:{line}. If .qa/context.md was unavailable, say so and name whatever
source you used instead (docstring, README, etc.), or say plainly that no
documented expectation was found and the assertion looks like a directly
observed behavioral gap.}

**Owners:** {@owner, @org/team, ...} (from CODEOWNERS: {matched pattern})

**We did not change any code.** This needs a human decision about which is
correct — {the documented/expected behavior} or {the current implementation}.

**What should happen next?** Reply here. Only maintainers' replies are acted on, at the next pipeline run.
- `/qa fix` (optionally: how it should behave): the pipeline opens a PR fixing the code; you review and merge it
- `/qa not-a-bug` (optionally: why, and what's correct): the pipeline updates its test to the behaviour you confirm and closes this issue
- `/qa wont-fix` (optionally: why): the test is kept as a known failure linked here, and this issue is closed
- `/qa later`: pauses reminders for 30 days

Plain words work too; the pipeline asks if it isn't sure what you meant.
