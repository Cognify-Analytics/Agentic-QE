<!--
Template for issues /triage-tests files for COMPLEX/AMBIGUOUS failures.
Fill every {placeholder}. Omit the "Suggested owner" line entirely if
scripts/resolve_owners.py found no owner (see its --no-owner-found behavior)
rather than leaving a placeholder or guessing one.
-->
Title: [QA Pipeline] {short description of the suspected defect}

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

**Suggested owner:** {@owner} (from CODEOWNERS: {matched path})

**We did not change any code.** This needs a human decision about which is
correct — {the documented/expected behavior} or {the current implementation}.
