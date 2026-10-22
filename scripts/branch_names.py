#!/usr/bin/env python3
"""Decide the names of every branch the pipeline pushes.

One place for the naming rule, so the GitHub Actions workflow and the
skills can never disagree about it.

Usage:
    python scripts/branch_names.py --branch <triggering branch> --sha <short sha>
                                   [--clickup] [--task-id <id>]

Default naming (no --clickup):

    auto-fix/triage-<sha>                     SIMPLE test fixes
    auto-fix/bugfix-issue-<n>                 bug fixes (fix_bugs, or a maintainer's /qa fix)
    auto-fix/qa-decision-issue-<n>            test updates after /qa not-a-bug or /qa wont-fix
    agentic-qe/qa-baseline-<sha>              .qa/ baseline (workflow only)

ClickUp naming (--clickup), for repos whose branch policy requires a ClickUp
task ID. The ID is taken from the branch that triggered the run, so the
pipeline's branches inherit the developer's task instead of needing a new
one -- run on bug/CU-101010-cache-loading and you get:

    auto-fix/CU-101010-triage-<sha>
    auto-fix/CU-101010-bugfix-issue-<n>
    auto-fix/CU-101010-qa-decision-issue-<n>
    auto-fix/CU-101010-qa-baseline-<sha>

The ID is the first CU-<letters/digits> segment of the branch name, matched
case-insensitively and always written back as "CU-". --task-id is only a
fallback for when the branch has none (e.g. a workflow_dispatch on main);
it may be given with or without the "CU-" prefix.

Prints JSON to stdout:

    {"clickup": true, "task_id": "101010", "task_id_source": "branch",
     "branches": {"triage": "auto-fix/CU-101010-triage-a1b2c3d",
                  "bugfix": "auto-fix/CU-101010-bugfix-issue-{issue_number}",
                  "decision": "auto-fix/CU-101010-qa-decision-issue-{issue_number}",
                  "qa_baseline": "auto-fix/CU-101010-qa-baseline-a1b2c3d"},
     "problem": null}

"bugfix" and "decision" are templates: replace {issue_number} with the
issue's number.
With --clickup and no usable ID anywhere, "branches" is null and "problem"
says why. The pipeline must then push no branch at all -- a branch outside
the naming policy is exactly what this option exists to prevent. Always
exits 0; the caller decides what to do with "problem".
"""

import argparse
import json
import re
import sys

BRANCH_TASK_ID = re.compile(r"(?:^|[/_-])CU-([A-Za-z0-9]+)", re.IGNORECASE)
TASK_ID = re.compile(r"^(?:CU-)?([A-Za-z0-9]+)$", re.IGNORECASE)


def branch_names(branch, sha, clickup=False, task_id_fallback=None):
    result = {"clickup": clickup, "task_id": None, "task_id_source": None, "branches": None, "problem": None}

    if not clickup:
        result["branches"] = {
            "triage": f"auto-fix/triage-{sha}",
            "bugfix": "auto-fix/bugfix-issue-{issue_number}",
            "decision": "auto-fix/qa-decision-issue-{issue_number}",
            "qa_baseline": f"agentic-qe/qa-baseline-{sha}",
        }
        return result

    match = BRANCH_TASK_ID.search(branch or "")
    if match:
        result["task_id"], result["task_id_source"] = match.group(1), "branch"
    elif task_id_fallback:
        fallback = TASK_ID.match(task_id_fallback.strip())
        if not fallback:
            result["problem"] = (
                f"clickup_task_id '{task_id_fallback}' is not a ClickUp task ID "
                "(expected letters and digits, optionally prefixed with CU-)"
            )
            return result
        result["task_id"], result["task_id_source"] = fallback.group(1), "input"
    else:
        result["problem"] = (
            f"ClickUp branch naming is on, but branch '{branch}' has no CU-<task id> in its "
            "name and no clickup_task_id was given -- no branch will be pushed"
        )
        return result

    prefix = f"auto-fix/CU-{result['task_id']}"
    result["branches"] = {
        "triage": f"{prefix}-triage-{sha}",
        "bugfix": f"{prefix}-bugfix-issue-{{issue_number}}",
        "decision": f"{prefix}-qa-decision-issue-{{issue_number}}",
        "qa_baseline": f"{prefix}-qa-baseline-{sha}",
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--branch", required=True, help="the branch that triggered this run")
    parser.add_argument("--sha", required=True, help="short SHA of the commit under test")
    parser.add_argument("--clickup", action="store_true", help="name branches after the ClickUp task ID")
    parser.add_argument("--task-id", default="", help="fallback task ID when the branch has none")
    args = parser.parse_args()

    print(json.dumps(branch_names(args.branch, args.sha, args.clickup, args.task_id), indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
