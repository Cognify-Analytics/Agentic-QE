#!/usr/bin/env python3
"""Write a run's durable record into .qa/runs/: the part of a run that outlives it.

.claude-pipeline/ is scratch. It is rewritten every run and gitignored, and on
a CI runner it is thrown away with the machine; its raw logs are too large and
too raw to commit. This script distils what a teammate needs to know about a
run, later, into files committed with the rest of .qa/:

    .qa/runs/<stem>.md     the run for people: when, where, by whom and on
        which model it ran, what it wrote and found, how each failure was
        classified and why, what it filed, what needs a human, and the runs
        recorded before it
    .qa/runs/<stem>.json   the same for scripts and the Agentic QE dashboard
        (schema_version 2, see RUN-FILE-CONTRACT.md): repository and run
        identity, the orchestrator's run record, the tests and triage results,
        telemetry (model, effort, turns, tokens, duration, cost), and every
        issue and PR it filed or drafted
    .qa/runs/README.md     explaining the folder

<stem> is the run's real UTC start time, the commit and where it ran:

    local  <YYYY-MM-DDTHHMMSSZ>-<sha7>-local-<rand6>
    CI     <YYYY-MM-DDTHHMMSSZ>-<sha7>-ci-<GITHUB_RUN_ID>-<GITHUB_RUN_ATTEMPT>

Names sort in run order. Both files are claimed together with exclusive
create, so an existing record is never replaced: a local run retries with a
new <rand6>, a CI run (whose name is fixed) writes nothing rather than
overwrite. A run only ever adds files, so two branches recording runs never
conflict.

Run after collect_telemetry.py, the same way for every kind of run:
    ci                 the workflow's "Write the run record" step
    local-interactive  /test-pipeline's Finish step 5
    local-headless     scripts/run_local.py

Usage:
    python scripts/record_run.py [--pipeline-dir .claude-pipeline] [--qa-dir .qa]
        [--actor NAME] [--event NAME] [--repo OWNER/NAME] [--repo-id N]
        [--visibility public|private] [--run-id ID] [--run-attempt N] [--workflow-sha SHA]

Reads run.json, stages.json, run-record.json (written by /test-pipeline),
00-followup.json, 01-tests.json, 03-triage.json, summary.md and
telemetry.json from --pipeline-dir; any of them may be missing. Writes
nothing for a follow-up-only run, which is a reply to one issue comment,
not a pipeline run. If the orchestrator never wrote run-record.json (a
crash, the turn limit), the record is still written, marked "incomplete",
from whatever the stages left. Never exits non-zero.
"""

import argparse
import glob
import json
import os
import re
import secrets
import string
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_trace import cell, code, fmt_duration, load_json, one_line, parse_ts, redact  # noqa: E402

SCHEMA_VERSION = 2
HISTORY_LIMIT = 15
NAME_ATTEMPTS = 5
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")

README = """# Agentic QE run history

Every run of the Agentic QE pipeline, on a developer's machine or in CI,
adds two files here with the same name:

- **`<stem>.md`**: the run, for people. It covers where, by whom and on
  which model it ran; the tests it wrote; every failure and why it was
  classified that way; the issues and PRs it filed; what needs a human;
  and a table of the runs before it. Start with the newest one.
- **`<stem>.json`**: the same run for scripts and the Agentic QE
  dashboard, including cost, token and turn telemetry.

The stem is the run's UTC start time, the commit, and where it ran:

| Run | Name |
|---|---|
| Local | `<YYYY-MM-DDTHHMMSSZ>-<sha7>-local-<rand6>` |
| GitHub Actions | `<YYYY-MM-DDTHHMMSSZ>-<sha7>-ci-<run id>-<run attempt>` |

Names sort in run order, so the newest run is last. Files are only ever
added, never edited or replaced. Older records are named
`<date>-<commit>.json` (before plugin 0.4.1) or `<date>-<time>-<commit>`
(0.4.1 to 0.4.2).

The full step-by-step trace is not kept in the repo, because it is raw
command output and large. A CI run's trace is in that run's GitHub Actions
artifacts. A local run's trace stays in `.claude-pipeline/` on the machine
that ran it.

Written by [Agentic QE](https://github.com/Cognify-Analytics/Agentic-QE).
"""

# run.source in the record: telemetry's "ci" is written as "github-actions".
SOURCE_NAMES = {"ci": "github-actions"}

SOURCES = {
    "github-actions": "GitHub Actions",
    "ci": "GitHub Actions",
    "local-interactive": "Local Claude Code session",
    "local-headless": "Local headless run (scripts/run_local.py)",
}

MODES = {"live": "live", "report-only": "report_only", "report_only": "report_only"}

# Keys of the record this script owns; the orchestrator's run-record.json supplies the rest.
OWN_KEYS = ("schema_version", "name", "sharing", "generator", "repository", "run",
            "tests", "triage", "telemetry", "github", "follow_up", "trace")

TESTS_KEYS = ("language", "framework", "test_command", "test_location", "files_created", "files_modified",
              "modules_skipped", "coverage_shortfall", "tests_removed", "tests_flagged_as_possible_bugs",
              "tooling_gaps", "notes", "stacks")

TRIAGE_KEYS = ("classifications", "fixes_applied", "issues_commented", "issues_existing",
               "escalated", "acknowledged", "tooling_gaps")


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def git(*args, cwd=None):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10, cwd=cwd)
    except (OSError, subprocess.SubprocessError):
        return None
    return (out.stdout.strip() or None) if out.returncode == 0 else None


def pick(d, *keys):
    """The keys of d that are present, in the order given."""
    return {k: d[k] for k in keys if k in d}


def no_none(d):
    return {k: v for k, v in d.items() if v is not None}


def scrub(value):
    """Redact tokens from every string in a JSON value before it is committed."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


def iso(ts):
    return f"{ts:%Y-%m-%dT%H:%M:%SZ}"


def real_time(value):
    """value as a whole-second UTC datetime, or None when it can't be a real
    start time: missing, date-only, without a timezone, or exactly midnight
    UTC (what a date turned into a time looks like)."""
    if not isinstance(value, str) or "T" not in value:
        return None
    ts = parse_ts(value)
    if ts is None or ts.tzinfo is None:
        return None
    ts = ts.astimezone(timezone.utc).replace(microsecond=0)
    return None if (ts.hour, ts.minute, ts.second) == (0, 0, 0) else ts


def start_time(run, pdir):
    """When the run really started: run.json's timestamp, or, if that is not a
    real time, when run.json was written (the pipeline writes it before Stage 1)."""
    ts = real_time(run.get("timestamp"))
    if ts:
        return ts
    try:
        written = datetime.fromtimestamp(os.path.getmtime(os.path.join(pdir, "run.json")), timezone.utc)
    except OSError:
        written = datetime.now(timezone.utc)
    print(f"record_run: run.json's timestamp {run.get('timestamp')!r} is not a real start time; "
          "using the time run.json was written instead.")
    return written.replace(microsecond=0)


def github_full_name(value):
    """owner/repo from a GitHub remote URL (https or ssh) or an owner/repo string.
    None for anything else: never a folder name or another host."""
    if not value:
        return None
    value = value.strip().rstrip("/")
    value = value[:-4] if value.endswith(".git") else value
    for sep in ("github.com:", "github.com/"):
        if sep in value:
            value = value.split(sep, 1)[1]
            break
    else:
        if "://" in value or "@" in value:
            return None
    parts = value.split("/")
    if len(parts) == 2 and all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts):
        return value
    return None


def repository_block(args, run, tel):
    full_name = (github_full_name(args.repo) or github_full_name(tel.get("repo"))
                 or github_full_name((run.get("local") or {}).get("repo"))
                 or github_full_name(git("remote", "get-url", "origin")))
    if not full_name:
        print("record_run: no GitHub remote named origin, so repository.full_name is left out; "
              "the dashboard loader will need --repo owner/name for this record.")
    default_branch = (run.get("ci") or {}).get("default_branch") or (run.get("local") or {}).get("default_branch")
    if not default_branch:
        head = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        default_branch = head.split("/", 1)[1] if head and "/" in head else None
    return no_none({
        "provider": "github",
        "provider_repo_id": int(args.repo_id) if args.repo_id.isdigit() else None,
        "full_name": full_name,
        "owner": full_name.split("/")[0] if full_name else None,
        "default_branch": default_branch,
        "visibility": args.visibility or None,
    })


def generator_block(args):
    """Which Agentic QE wrote the record: its version, and its commit when this
    script runs from a git checkout of it (CI's .agentic-qe, or --plugin-dir)."""
    manifest = load_json(os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json")) or {}
    sha = None
    top = git("rev-parse", "--show-toplevel", cwd=PLUGIN_ROOT)
    if top and os.path.normcase(os.path.realpath(top)) == os.path.normcase(os.path.realpath(PLUGIN_ROOT)):
        sha = git("rev-parse", "HEAD", cwd=PLUGIN_ROOT)
    return no_none({
        "ref": f"v{manifest['version']}" if manifest.get("version") else None,
        "sha": sha,
        "workflow_sha": args.workflow_sha or None,
    })


def sha7(sha):
    short = (sha or "")[:7].lower()
    return short if re.fullmatch(r"[0-9a-f]{7}", short) else "unknown"


def claim_run_files(qa_runs, make_stem, attempts):
    """Reserve <stem>.json and <stem>.md together, never replacing a file that
    exists. Returns the stem, or None when every name tried was taken."""
    for _ in range(attempts):
        stem = make_stem()
        claimed = []
        try:
            for ext in (".json", ".md"):
                path = os.path.join(qa_runs, stem + ext)
                os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                claimed.append(path)
            return stem
        except FileExistsError:
            for path in claimed:
                os.remove(path)
    return None


def stack_values(value, key):
    """{stack or None: value[key]} from a flat {key: n} or a per-stack {stack: {key: n}}."""
    if not isinstance(value, dict):
        return {}
    if key in value:
        return {None: value.get(key)}
    return {name: v.get(key) for name, v in value.items() if isinstance(v, dict)}


def fmt_stacks(values, suffix=""):
    parts = [(f"{name} " if name else "") + f"{v}{suffix}" for name, v in values.items() if v is not None]
    return ", ".join(parts) or "–"


def fallback_record(run, stages, tests, triage):
    """What an orchestrator that never reached Finish would have recorded."""
    coverage = {}
    for name, stack in (tests.get("stacks") or {}).items():
        if isinstance(stack, dict) and isinstance(stack.get("coverage"), dict):
            coverage[name] = stack["coverage"]
    return {
        "date": (run.get("timestamp") or "")[:10] or None,
        "sha": run.get("sha"),
        "branch": run.get("branch"),
        "mode": "live" if run.get("live") else "report_only",
        "strategy": (run.get("ci") or {}).get("strategy"),
        "stages": stages or {},
        "coverage": coverage or tests.get("coverage") or tests.get("coverage_by_stack"),
        "tests_created": len(tests.get("files_created") or []) if tests else None,
        "tests_flagged_as_possible_bugs": len(tests.get("tests_flagged_as_possible_bugs") or []) if tests else None,
        "triage_totals": triage.get("totals_by_stack") or triage.get("totals") if triage else None,
        "status": "incomplete",
        "reason": "the orchestrator stopped before writing its run record (a crash or the turn limit); "
                  "this record was built from the stage outputs that exist",
    }


def flat_record(record, run, stages, triage):
    """The orchestrator's run record, in the contract's terms: mode live or
    report_only, a stage not reached as skipped:not-reached, triage_totals
    flat, and complex_issues counted from the classifications."""
    flat = {k: v for k, v in record.items() if k not in OWN_KEYS}
    flat["status"] = record.get("status") or "ok"
    flat["mode"] = MODES.get(record.get("mode")) or ("live" if run.get("live") else "report_only")
    flat["stages"] = {k: "skipped:not-reached" if v == "not_reached" else v
                      for k, v in (record.get("stages") or stages or {}).items()}

    # The dashboard reads flat totals. A multi-stack record's are per stack; the
    # sum across stacks is 03-triage.json's own "totals", and the split is kept.
    totals = flat.get("triage_totals")
    if isinstance(triage.get("totals"), dict) and not (isinstance(totals, dict) and "failed" in totals):
        by_stack = triage.get("totals_by_stack") or totals
        flat["triage_totals"] = pick(triage["totals"], "tests", "passed", "failed")
        if by_stack:
            flat["triage_totals_by_stack"] = by_stack

    if isinstance(triage.get("classifications"), list):
        classes = [c for c in triage["classifications"] if isinstance(c, dict)]
        flat["complex_issues"] = sum(1 for c in classes if str(c.get("type", "")).upper() == "COMPLEX")
        failed = (flat.get("triage_totals") or {}).get("failed")
        if isinstance(failed, int) and failed != len(classes):
            print(f"record_run: {failed} tests failed but {len(classes)} were classified; "
                  "the dashboard counts real bugs from the classifications only.")
    return flat


def tests_block(tests):
    return pick(tests, *TESTS_KEYS) or None


def triage_block(triage):
    if not triage:
        return None
    block = pick(triage, *TRIAGE_KEYS)
    # Left out, not [], when triage never classified: the dashboard then shows
    # real bugs as unknown rather than zero.
    if isinstance(triage.get("classifications"), list):
        block["classifications"] = [
            {**c, "type": str(c["type"]).upper()} if c.get("type") else c
            for c in triage["classifications"] if isinstance(c, dict)]
    return block


def telemetry_block(tel):
    if not tel:
        return None
    usage = tel.get("usage") or {}
    block = no_none({
        "model": tel.get("model_used") or tel.get("model"),
        "effort": tel.get("effort"),
        "max_turns": tel.get("max_turns"),
        "num_turns": tel.get("num_turns"),
        "duration_ms": tel.get("duration_ms"),
        "conclusion": tel.get("conclusion"),
        "usage": {k: int(usage[k]) for k in USAGE_KEYS if usage.get(k) is not None} or None,
    })
    # Unknown cost stays null, with cost_source saying why, never 0.
    block["cost_usd"] = tel.get("cost_usd")
    if tel.get("cost_source"):
        block["cost_source"] = tel["cost_source"]
    return block


def github_activity(triage):
    """The issues and PRs this run opened or drafted. An item without a URL is
    a draft (report_only), whatever else it says. Issues the run only commented
    on stay in triage.issues_commented, so they are never counted as filed."""
    issues, prs = [], []
    for i in triage.get("issues_created") or []:
        if not isinstance(i, dict):
            continue
        url = i.get("url") or None
        issue = {"url": url, "test": i.get("test"), "reason": i.get("reason"),
                 "report_only": bool(i.get("report_only")) or not url,
                 **pick(i, "title", "stack", "owners", "assignees", "mention_only", "assignment_error")}
        if issue["report_only"] and i.get("drafted_body"):
            issue["body"] = i["drafted_body"].strip()
        issues.append(issue)

    planned = triage.get("pr_planned") or {}
    if triage.get("pr_url") or planned:
        url = triage.get("pr_url") or None
        prs.append({"url": url, "kind": "auto_fix", "summary": planned.get("summary"), "report_only": not url,
                    **pick(planned, "branch", "files_changed", "owners", "assignees", "reviewers", "assignment_error")})
    for b in triage.get("bug_fix_prs_created") or []:
        if not isinstance(b, dict):
            continue
        url = b.get("pr_url") or None
        pr = {"url": url, "kind": "bug_fix", "test": b.get("test"), "summary": b.get("summary"),
              "report_only": bool(b.get("report_only")) or not url,
              **pick(b, "issue_url", "stack", "owners", "assignees", "reviewers", "assignment_error")}
        if b.get("file_changed"):
            pr["files_changed"] = [b["file_changed"]]
        prs.append(pr)
    return {"issues": issues, "prs": prs}


def follow_up_block(followup):
    """Stage 0's actions on issues filed by earlier runs. Kept apart from
    github.issues/prs: they are not issues this run filed, and a follow-up PR
    is not a bug fix."""
    actions = [pick(a, "issue", "url", "fingerprint", "test_status", "decision", "decided_by",
                    "action", "pr_url", "reason", "report_only")
               for a in followup.get("actions") or [] if isinstance(a, dict)]
    return {"actions": actions} if actions else None


def build_json(name, ident, run, record, stages, tests, triage, followup, telemetry):
    tel = telemetry or {}
    return no_none({
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "sharing": "findings",
        "generator": ident["generator"],
        "repository": ident["repository"],
        "run": ident["run"],
        **flat_record(record, run, stages, triage),
        "tests": tests_block(tests),
        "triage": triage_block(triage),
        "telemetry": telemetry_block(tel),
        "github": github_activity(triage),
        "follow_up": follow_up_block(followup),
    })


def tokens(n):
    if not n:
        return "0"
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)


def strip_summary(text):
    """summary.md without its title line and without the local "Please commit" list."""
    lines = (text or "").strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    out, skipping = [], False
    for line in lines:
        if line.startswith("## "):
            skipping = line.strip().lower() == "## please commit"
        if not skipping:
            out.append(line)
    return redact("\n".join(out).strip())


def history_rows(qa_runs, current):
    rows = []
    for path in glob.glob(os.path.join(qa_runs, "*.json")):
        data = load_json(path)
        if not isinstance(data, dict) or os.path.basename(path) == f"{current}.json":
            continue
        base = os.path.splitext(os.path.basename(path))[0]
        meta = data.get("run") or {}
        rows.append((meta.get("started_at") or meta.get("started") or data.get("date") or base, base, data))
    rows.sort(key=lambda r: r[0], reverse=True)
    return rows[:HISTORY_LIMIT], len(rows)


def history_section(qa_runs, current):
    rows, total = history_rows(qa_runs, current)
    if not rows:
        return ["## Earlier runs", "", "None recorded on this branch: this is the first.", ""]
    out = ["## Earlier runs", "",
           "| When (UTC) | Commit | Where | Model | Tests written | Coverage after | Failed | Record |",
           "|---|---|---|---|---|---|---|---|"]
    for started, base, data in rows:
        when = started.replace("T", " ")[:16] if "T" in str(started) else str(started)
        where = SOURCES.get((data.get("run") or {}).get("source"), "–")
        model = ((data.get("telemetry") or {}).get("model")) or "–"
        failed = sum(v or 0 for v in stack_values(data.get("triage_totals"), "failed").values())
        ext = "md" if os.path.exists(os.path.join(qa_runs, base + ".md")) else "json"
        link = f"[{ext}]({base}.{ext})"
        out.append(f"| {when} | `{data.get('sha', '?')}` | {cell(where, 40)} | {cell(model, 30)} | "
                   f"{data.get('tests_created', '–')} | {cell(fmt_stacks(stack_values(data.get('coverage'), 'after'), '%'), 80)} | "
                   f"{failed if data.get('triage_totals') else '–'} | {link} |")
    if total > len(rows):
        out.append(f"| … | | | | | | | {total - len(rows)} older in this folder |")
    return out + [""]


def build_markdown(name, rec, triage, summary_text, qa_runs):
    tel = rec.get("telemetry") or {}
    usage = tel.get("usage") or {}
    meta = rec["run"]
    started = parse_ts(meta.get("started_at"))
    when = f"{started.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC" if started else name
    where = SOURCES.get(meta.get("source"), meta.get("source") or "unknown")
    if meta.get("run_url"):
        where = f"[{where} run]({meta['run_url']})"
    if meta.get("event") and meta["event"] != "local":
        where += f", on `{meta['event']}`" + (f" for PR #{meta['pr_number']}" if meta.get("pr_number") else "")
    if meta.get("by"):
        where += f", started by {meta['by']}"
    took = fmt_duration((tel.get("duration_ms") or 0) / 1000) if tel.get("duration_ms") else "–"
    if tel.get("num_turns") is not None:
        took += f" · {tel['num_turns']} turns"
    tokens_in = sum(usage.get(k) or 0 for k in USAGE_KEYS if k != "output_tokens")
    if tokens_in or usage.get("output_tokens"):
        took += f" · {tokens(tokens_in)} in / {tokens(usage.get('output_tokens'))} out tokens"
    took += f" · cost {'$%.2f' % tel['cost_usd'] if tel.get('cost_usd') is not None else 'not recorded'}"

    status = rec.get("status", "ok")
    status_text = {"ok": "Finished"}.get(status, status)
    if rec.get("stopped_at"):
        status_text += f" at `{rec['stopped_at']}`"
    if rec.get("reason") and status != "ok":
        status_text += f": {one_line(rec['reason'], 300)}"

    out = [f"# Agentic QE run — {when}", "",
           "| | |", "|---|---|",
           f"| Commit | `{rec.get('sha', '?')}` on `{rec.get('branch', '?')}` |",
           f"| Where | {where} |",
           f"| Mode | {rec.get('mode', '?')}" + (", fix_bugs on" if meta.get("fix_bugs") else "") + " |",
           f"| Strategy | {rec.get('strategy', '–')} |",
           f"| Model / effort | `{tel.get('model') or '?'}` / `{tel.get('effort') or '?'}` |",
           f"| Took | {took} |",
           f"| Outcome | {status_text} |", ""]

    if summary_text:
        out += [summary_text, ""]
    else:
        out += ["_The run wrote no summary._", ""]

    classes = (rec.get("triage") or {}).get("classifications") or []
    if classes:
        out += ["## How each failure was classified", "", "| Test | Verdict | Why |", "|---|---|---|"]
        out += [f"| {code(c.get('test', '?'), 80)} | {cell(c.get('type', '?'), 20)} | {cell(redact(c.get('reason', '')), 400)} |"
                for c in classes]
        out.append("")

    gh = rec.get("github") or {}
    lines = []
    for i in gh.get("issues", []):
        if i.get("url") and not i.get("report_only"):
            lines.append(f"- Issue {i['url']} (filed)" + (f": {code(i['test'], 120)}" if i.get("test") else ""))
    for i in triage.get("issues_commented") or []:
        if isinstance(i, dict) and i.get("url"):
            lines.append(f"- Issue {i['url']} (commented on)" + (f": {code(i['test'], 120)}" if i.get("test") else ""))
    for a in (rec.get("follow_up") or {}).get("actions", []):
        if a.get("url") and a.get("action") not in (None, "none") and not a.get("report_only"):
            lines.append(f"- Issue {a['url']} (followed up: {a['action']})"
                         + (f", PR {a['pr_url']}" if a.get("pr_url") else ""))
    for p in gh.get("prs", []):
        if p.get("url") and not p.get("report_only"):
            kind = {"auto_fix": "test fixes", "bug_fix": "bug fix"}.get(p.get("kind"), p.get("kind"))
            lines.append(f"- PR {p['url']} ({kind})" + (f": {one_line(p['summary'], 160)}" if p.get("summary") else ""))
    if lines:
        out += ["## On GitHub", "", *lines, ""]

    drafts = [i for i in gh.get("issues", []) if i.get("report_only") and i.get("body")]
    if drafts:
        out += ["## Issues drafted but not filed (report-only)", ""]
        for i in drafts:
            out += [f"<details><summary>{code(i.get('test') or '?', 120)}: {cell(i.get('reason') or '', 160)}</summary>", "",
                    i["body"], "", "</details>", ""]

    out += history_section(qa_runs, name)
    trace_where = (f"in the [run's artifacts]({meta['run_url']})" if meta.get("run_url")
                   else "in `.claude-pipeline/trace.md` on the machine that ran it")
    out += ["---", "",
            f"The full step-by-step trace isn't kept in the repo. It is {trace_where}. "
            f"Machine-readable record: [`{name}.json`]({name}.json).", ""]
    return "\n".join(out)


def write_readme(qa_runs):
    """Write README.md, or bring an older one this script wrote up to date."""
    path = os.path.join(qa_runs, "README.md")
    current = read_text(path)
    if current is None or (current.startswith("# Agentic QE run history") and current != README):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(README)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pipeline-dir", default=".claude-pipeline")
    parser.add_argument("--qa-dir", default=".qa")
    parser.add_argument("--actor", default="", help="CI: who started the run (github.actor)")
    parser.add_argument("--event", default="", help="CI: what started it (github.event_name)")
    parser.add_argument("--repo", default="", help="owner/name; default: telemetry, then the origin remote")
    parser.add_argument("--repo-id", default="", help="CI: the numeric repository id (github.repository_id)")
    parser.add_argument("--visibility", default="", help="CI: public or private")
    parser.add_argument("--run-id", default="", help="CI: github.run_id")
    parser.add_argument("--run-attempt", default="", help="CI: github.run_attempt")
    parser.add_argument("--workflow-sha", default="", help="CI: the reusable workflow's commit")
    args = parser.parse_args()

    pdir = args.pipeline_dir
    run = load_json(os.path.join(pdir, "run.json")) or {}
    if not run:
        print("record_run: no run.json, so the pipeline never started; nothing to record.")
        return
    if (run.get("ci") or {}).get("strategy") == "follow-up-only":
        print("record_run: follow-up-only run (a reply to one issue comment); nothing to record.")
        return

    stages = load_json(os.path.join(pdir, "stages.json"))
    tests = load_json(os.path.join(pdir, "01-tests.json")) or {}
    triage = load_json(os.path.join(pdir, "03-triage.json")) or {}
    followup = load_json(os.path.join(pdir, "00-followup.json")) or {}
    telemetry = load_json(os.path.join(pdir, "telemetry.json"))
    record = load_json(os.path.join(pdir, "run-record.json"))
    if not isinstance(record, dict):
        record = fallback_record(run, stages, tests, triage)
    tel = telemetry or {}

    ci = run.get("mode") == "ci" or tel.get("source") == "ci"
    source = tel.get("source") or ("ci" if ci else None)
    run_id = args.run_id or (str(tel["run_id"]) if ci and tel.get("run_id") else "")
    attempt = int(args.run_attempt) if args.run_attempt.isdigit() else 1
    started = start_time(run, pdir)
    finished = max(datetime.now(timezone.utc).replace(microsecond=0), started)
    prefix = f"{started:%Y-%m-%dT%H%M%SZ}-{sha7(run.get('sha'))}"
    if ci and run_id:
        make_stem, attempts = (lambda: f"{prefix}-ci-{run_id}-{attempt}"), 1
    else:
        alphabet = string.ascii_lowercase + string.digits
        make_stem, attempts = (lambda: f"{prefix}-local-{''.join(secrets.choice(alphabet) for _ in range(6))}"), NAME_ATTEMPTS

    qa_runs = os.path.join(args.qa_dir, "runs")
    os.makedirs(qa_runs, exist_ok=True)
    name = claim_run_files(qa_runs, make_stem, attempts)
    if name is None:
        print(f"record_run: {qa_runs}/{make_stem()}.json already exists; an existing record is never "
              "replaced, so this run was not recorded.", file=sys.stderr)
        return

    sha = run.get("sha")
    ident = {
        "generator": generator_block(args),
        "repository": repository_block(args, run, tel),
        # run_url and pr_number are written as null, not left out, like the contract's samples.
        "run": {k: v for k, v in {
            "provider_run_id": run_id if ci and run_id else name,
            "run_attempt": attempt,
            "source": SOURCE_NAMES.get(source, source),
            "by": args.actor or (git("config", "user.name") if not ci else None),
            "event": args.event or ("local" if not ci else None),
            "run_url": tel.get("run_url") or (run.get("ci") or {}).get("run_url") or None,
            "pr_number": tel.get("pr_number") or (run.get("ci") or {}).get("pr_number"),
            "sha": git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}") if sha else None,
            "branch": run.get("branch"),
            "started_at": iso(started),
            "started": iso(started),  # the pre-0.4.3 name, kept for one release
            "finished_at": iso(finished),
            "conclusion": tel.get("conclusion"),
            "fix_bugs": run.get("fix_bugs"),
        }.items() if v is not None or k in ("run_url", "pr_number")},
    }

    paths = [os.path.join(qa_runs, name + ext) for ext in (".json", ".md")]
    try:
        rec = scrub(build_json(name, ident, run, record, stages, tests, triage, followup, telemetry))
        rec.setdefault("sha", sha)
        rec.setdefault("branch", run.get("branch"))
        md = build_markdown(name, rec, triage, strip_summary(read_text(os.path.join(pdir, "summary.md"))), qa_runs)
        with open(paths[0], "w", encoding="utf-8", newline="\n") as f:
            json.dump(rec, f, indent=2)
            f.write("\n")
        with open(paths[1], "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
    except Exception:
        for path in paths:
            if os.path.exists(path):
                os.remove(path)
        raise
    write_readme(qa_runs)
    print(f"record_run: wrote {qa_runs}/{name}.md and .json")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- a missing record costs history, not the run
        print(f"record_run: {exc}", file=sys.stderr)
    sys.exit(0)
