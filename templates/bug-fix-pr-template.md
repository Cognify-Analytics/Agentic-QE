<!--
Template for the PR /triage-tests opens in Step 8.5, when the opt-in
fix_bugs mode produced a verified fix for a COMPLEX failure. This is a
separate PR from the routine SIMPLE-test-fix PR (Step 8) — it changes
production source, not a test, and carries a different review burden.

Every PR from this template links to the issue Step 7 already filed for
the same failure using "Relates to", never "Fixes"/"Closes" — merging
this PR must never auto-close the issue. A human decides separately
whether the underlying bug is actually resolved.

Fill every {placeholder}.
-->
Title: [QA Pipeline] Fix: {short description of the fix} (relates to #{issue_number})

> ⚠️ **AI-generated change to production source code.** This is not a
> routine test fix — it changes what the code *does*, not just how it's
> tested. Review it with the same scrutiny you'd give a human-authored PR.
> Do not merge on trust alone, and do not merge without at least one
> human approval.

**Relates to:** #{issue_number}
**Failing test this addresses:** {test_name} ({test_file})
**File(s) changed:** {file_list}
**Owners:** {@owner, @org/team, ...} (from CODEOWNERS -- omit this line if none)
**Detected at:** {git_sha}

**What changed and why**
{one or two lines: what the code did before, what it does now, and the
specific documented expectation — a .qa/context.md line, a docstring, or
adjacent docs — that justified the change. If the evidence is a docstring
or doc line, quote it.}

**Verification**
- Target test ({test_name}): {passed/failed}
- Full suite for this stack: {passed/failed} ({n} passed, {n} failed)

**This PR was not merged by the pipeline, and merging it does not close
#{issue_number} automatically.** The issue stays open until a human
reviews this fix and closes it themselves.
