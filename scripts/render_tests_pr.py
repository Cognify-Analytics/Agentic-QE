#!/usr/bin/env python3
"""Write the title and body of the PR that carries a CI run's generated tests.

The workflow's "Record the run" step commits the tests /generate-tests wrote
(those no auto-fix PR already carries) together with .qa/, pushes them to the
pipeline's own branch and opens a PR with what this script prints. Tests and
.qa/ travel together so the inventory never names a test file the branch
doesn't have.

Usage:
    python scripts/render_tests_pr.py --files <list> --sha <short sha>
        [--pipeline-dir .claude-pipeline] [--run-url URL] [--report-only]
        --out <body file>

--files is a text file with one test path per line (what
check_test_only_changes.py --list-tests printed). Prints the PR title on
stdout and writes the body to --out. Reads 01-tests.json and 03-triage.json
when they exist and leaves out any section it has no data for, so a
half-finished run still gets a usable PR. Always exits 0.
"""

import argparse
import json
import os
import subprocess
import sys


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def is_tracked(path):
    return subprocess.run(["git", "ls-files", "--error-unmatch", "--", path],
                          capture_output=True).returncode == 0


def fmt_pct(value):
    return "n/a" if value is None else f"{value}%"


def coverage_rows(tests):
    """[(stack or None, before, after)] from any of the shapes 01-tests.json uses."""
    rows = []
    stacks = tests.get("stacks")
    if isinstance(stacks, dict):
        for name, stack in stacks.items():
            cov = (stack or {}).get("coverage")
            if isinstance(cov, dict) and ("before" in cov or "after" in cov):
                rows.append((name, cov.get("before"), cov.get("after")))
    by_stack = tests.get("coverage_by_stack")
    if not rows and isinstance(by_stack, dict):
        for name, cov in by_stack.items():
            if isinstance(cov, dict):
                rows.append((name, cov.get("before"), cov.get("after")))
    cov = tests.get("coverage")
    if not rows and isinstance(cov, dict) and ("before" in cov or "after" in cov):
        rows.append((None, cov.get("before"), cov.get("after")))
    return rows


def issue_links(triage):
    """{test name: issue URL or #number} from every issue list 03-triage.json keeps."""
    links = {}
    for key in ("issues_created", "issues_commented", "issues_existing", "acknowledged"):
        for entry in triage.get(key) or []:
            if not isinstance(entry, dict) or not entry.get("test"):
                continue
            where = entry.get("url") or (f"#{entry['issue']}" if entry.get("issue") else None)
            if where:
                links.setdefault(entry["test"], where)
    return links


def failing_on_purpose(tests, triage, files):
    """[(test, file, reason)] for the tests in this PR that are red on purpose."""
    in_pr = set(files)
    found, seen = [], set()
    for c in triage.get("classifications") or []:
        if isinstance(c, dict) and c.get("type") in ("COMPLEX", "AMBIGUOUS") and c.get("file") in in_pr:
            found.append((c.get("test", "?"), c["file"], c.get("reason", "")))
            seen.add(c.get("test"))
    for t in tests.get("tests_flagged_as_possible_bugs") or []:
        if isinstance(t, dict) and t.get("test") not in seen and (t.get("file") in in_pr or not t.get("file")):
            found.append((t.get("test", "?"), t.get("file") or "?", t.get("reason", "")))
    return found


def one_line(text, limit=240):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render(files, sha, tests, triage, run_url, report_only):
    out = []
    if report_only:
        out += ["> **Draft: this was a report-only run.** Nothing else was filed or opened. "
                "Mark this PR ready for review when you want the tests.", ""]
    out += [f"Tests written by the Agentic QE pipeline at `{sha}`, plus the `.qa/` record that "
            "describes them. No production source is touched.", ""]

    rows = coverage_rows(tests)
    if rows:
        out += ["### Coverage", ""]
        if rows[0][0] is None:
            out += ["| Before | After |", "|---|---|", f"| {fmt_pct(rows[0][1])} | {fmt_pct(rows[0][2])} |"]
        else:
            out += ["| Stack | Before | After |", "|---|---|---|"]
            out += [f"| `{name}` | {fmt_pct(before)} | {fmt_pct(after)} |" for name, before, after in rows]
        out.append("")

    out += [f"### Files ({len(files)})", ""]
    for path in files:
        state = "changed" if is_tracked(path) and os.path.exists(path) else ("deleted" if not os.path.exists(path) else "new")
        out.append(f"- `{path}` ({state})")
    out.append("")

    red = failing_on_purpose(tests, triage, files)
    if red:
        links = issue_links(triage)
        out += [f"### {len(red)} test(s) fail on purpose", "",
                "Each one asserts what the code is documented or clearly meant to do, and the code does "
                "something else. It is a suspected bug, not a broken test, and the pipeline will not weaken "
                "it. Merged as it is, this PR turns the suite red until each one is settled: fix the bug, "
                "or reply on its issue (`/qa not-a-bug`, `/qa wont-fix`) and the pipeline updates the test.", ""]
        for test, path, reason in red:
            issue = links.get(test)
            out.append(f"- `{test}` in `{path}`" + (f" ({issue})" if issue else "") + f": {one_line(reason)}")
        out.append("")

    gaps_out = []
    for s in tests.get("coverage_shortfall") or []:
        if isinstance(s, dict):
            gaps_out.append(f"- `{s.get('path', '?')}` stopped at {fmt_pct(s.get('coverage'))}: "
                            f"{one_line(s.get('reason') or s.get('uncovered'))}")
    # A stack with no test runner skips every module for the same reason: one line, not thirty.
    by_reason = {}
    for m in tests.get("modules_skipped") or []:
        if isinstance(m, dict):
            by_reason.setdefault(one_line(m.get("reason")), []).append(m.get("path", "?"))
    for reason, paths in by_reason.items():
        if len(paths) < 3:
            gaps_out += [f"- `{path}` has no tests: {reason}" for path in paths]
        else:
            gaps_out.append(f"- {len(paths)} modules have no tests (`{paths[0]}`, `{paths[1]}` and "
                            f"{len(paths) - 2} more): {reason}")
    if gaps_out:
        out += ["### Not covered, and why", ""] + gaps_out[:25]
        if len(gaps_out) > 25:
            out.append(f"- …and {len(gaps_out) - 25} more in the run artifact's `01-tests.json`")
        out.append("")

    tooling = [g for g in tests.get("tooling_gaps") or [] if isinstance(g, dict)]
    if tooling:
        out += ["### Missing test tooling", "",
                "Install steps (PowerShell and bash) are in `.qa/context.md`, section 5.", ""]
        for g in tooling:
            where = f"{g['stack']}: " if g.get("stack") else ""
            out.append(f"- {where}`{g.get('tool', '?')}`: {one_line(g.get('effect') or g.get('needed_for'))}")
        out.append("")

    out += ["Merging this is also what lets the next run go incremental instead of bootstrapping the "
            "whole repo again. The pipeline never merges its own PRs.", ""]
    if run_url:
        out.append(f"[Run log]({run_url})")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--files", required=True, help="one test path per line")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--pipeline-dir", default=".claude-pipeline")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--report-only", action="store_true", help="the run was report-only: say the PR is a draft")
    parser.add_argument("--out", required=True, help="where to write the PR body")
    args = parser.parse_args()

    with open(args.files, encoding="utf-8") as f:
        files = [line.strip() for line in f if line.strip()]
    tests = load_json(os.path.join(args.pipeline_dir, "01-tests.json")) or {}
    triage = load_json(os.path.join(args.pipeline_dir, "03-triage.json")) or {}

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(files, args.sha, tests, triage, args.run_url, args.report_only))
    print(f"Agentic QE: tests generated at {args.sha} ({len(files)} file{'s' if len(files) != 1 else ''})")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- a plain body beats no PR
        print(f"render_tests_pr: {exc}", file=sys.stderr)
        print("Agentic QE: generated tests")
    sys.exit(0)
