#!/usr/bin/env python3
"""Write a run's durable record into .qa/runs/: the part of a run that outlives it.

.claude-pipeline/ is scratch. It is rewritten every run and gitignored, and on
a CI runner it is thrown away with the machine; its raw logs are too large and
too raw to commit. This script distils what a teammate needs to know about a
run, later, into files committed with the rest of .qa/:

    .qa/runs/<yyyy-mm-dd>-<hhmm>-<sha>.md     the run for people: when, where,
        by whom and on which model it ran, what it wrote and found, how each
        failure was classified and why, what it filed, what needs a human, and
        the runs recorded before it
    .qa/runs/<yyyy-mm-dd>-<hhmm>-<sha>.json   the same for scripts: the
        orchestrator's run record, plus telemetry (model, effort, turns,
        tokens, duration, cost), who or what started it, and every issue and
        PR it filed or touched
    .qa/runs/README.md                        once, explaining the folder

The UTC start time in the name keeps a re-run at the same commit from
overwriting the earlier record, and makes names sort in run order. A run only
ever adds files, never edits an old one, so two branches recording runs never
conflict.

Run after collect_telemetry.py, the same way for every kind of run:
    ci                 the workflow's "Write the run record" step
    local-interactive  /test-pipeline's Finish step 5
    local-headless     scripts/run_local.py

Usage:
    python scripts/record_run.py [--pipeline-dir .claude-pipeline] [--qa-dir .qa]
        [--actor NAME] [--event NAME]

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
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_trace import cell, code, fmt_duration, load_json, one_line, parse_ts, redact  # noqa: E402

SCHEMA_VERSION = 2
HISTORY_LIMIT = 15

README = """# Agentic QE run history

Every run of the Agentic QE pipeline, on a developer's machine or in CI,
adds two files here:

- **`<date>-<time>-<commit>.md`**: the run, for people. It covers where,
  by whom and on which model it ran; the tests it wrote; every failure and
  why it was classified that way; the issues and PRs it filed; what needs a
  human; and a table of the runs before it. Start with the newest one.
- **`<date>-<time>-<commit>.json`**: the same run for scripts, including
  cost, token and turn telemetry.

Times are UTC, so names sort in run order and the newest run is last.
Files are only ever added, never edited. Records from before plugin 0.4.1
are JSON only, named `<date>-<commit>.json`.

The full step-by-step trace is not kept in the repo, because it is raw
command output and large. A CI run's trace is in that run's GitHub Actions
artifacts. A local run's trace stays in `.claude-pipeline/` on the machine
that ran it.

Written by [Agentic QE](https://github.com/Cognify-Analytics/Agentic-QE).
"""

SOURCES = {
    "ci": "GitHub Actions",
    "local-interactive": "Local Claude Code session",
    "local-headless": "Local headless run (scripts/run_local.py)",
}


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def git_user():
    try:
        out = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def record_name(run):
    ts = parse_ts(run.get("timestamp")) or datetime.now(timezone.utc)
    return f"{ts.astimezone(timezone.utc):%Y-%m-%d-%H%M}-{run.get('sha') or 'unknown'}"


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
        "mode": "live" if run.get("live") else "report-only",
        "strategy": (run.get("ci") or {}).get("strategy") or "local",
        "stages": stages or {},
        "coverage": coverage or tests.get("coverage") or tests.get("coverage_by_stack"),
        "tests_created": len(tests.get("files_created") or []) if tests else None,
        "tests_flagged_as_possible_bugs": len(tests.get("tests_flagged_as_possible_bugs") or []) if tests else None,
        "triage_totals": triage.get("totals_by_stack") or triage.get("totals") if triage else None,
        "status": "incomplete",
        "reason": "the orchestrator stopped before writing its run record (a crash or the turn limit); "
                  "this record was built from the stage outputs that exist",
    }


def github_activity(followup, triage):
    """Every issue and PR the run filed or touched, with URLs, from the stage outputs."""
    issues, prs = [], []
    for key, kind in (("issues_created", "filed"), ("issues_commented", "commented on"),
                      ("issues_existing", "already open")):
        for i in triage.get(key) or []:
            if isinstance(i, dict):
                issues.append({"kind": kind, "url": i.get("url"), "test": i.get("test"),
                               "report_only": bool(i.get("report_only")), "reason": i.get("reason")})
    if triage.get("pr_url") or triage.get("pr_planned"):
        planned = triage.get("pr_planned") or {}
        prs.append({"kind": "test fixes", "url": triage.get("pr_url"), "branch": planned.get("branch"),
                    "summary": planned.get("summary")})
    for b in triage.get("bug_fix_prs_created") or []:
        if isinstance(b, dict):
            prs.append({"kind": "bug fix", "url": b.get("pr_url"), "issue": b.get("issue_url"),
                        "summary": b.get("summary"), "file": b.get("file_changed")})
    for a in followup.get("actions") or []:
        if isinstance(a, dict) and a.get("action") not in (None, "none"):
            issues.append({"kind": f"followed up ({a['action']})", "url": a.get("url"),
                           "test": a.get("fingerprint"), "report_only": bool(a.get("report_only"))})
            if a.get("pr_url"):
                prs.append({"kind": f"follow-up ({a['action']})", "url": a.get("pr_url"), "issue": a.get("url")})
    return {"issues": issues, "prs": prs}


def build_json(name, run, record, telemetry, activity, args):
    tel = telemetry or {}
    usage = tel.get("usage") or {}
    return {
        **record,
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "status": record.get("status") or "ok",
        "run": {
            "source": tel.get("source"),
            "by": args.actor or (git_user() if (tel.get("source") or "").startswith("local") else None),
            "event": args.event or None,
            "run_url": tel.get("run_url"),
            "pr_number": tel.get("pr_number"),
            "started": run.get("timestamp"),
            "fix_bugs": run.get("fix_bugs"),
        },
        "telemetry": {
            "model": tel.get("model_used") or tel.get("model"),
            "effort": tel.get("effort"),
            "num_turns": tel.get("num_turns"),
            "duration_ms": tel.get("duration_ms"),
            "cost_usd": tel.get("cost_usd"),
            "cost_source": tel.get("cost_source"),
            "input_tokens": sum(int(usage.get(k) or 0) for k in
                                ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "conclusion": tel.get("conclusion"),
        } if telemetry else None,
        "github": activity,
    }


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
        rows.append((data.get("run", {}).get("started") or data.get("date") or base, base, data))
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


def build_markdown(name, run, rec, triage, summary_text, qa_runs):
    tel = rec.get("telemetry") or {}
    meta = rec["run"]
    started = parse_ts(run.get("timestamp"))
    when = f"{started.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC" if started else name
    where = SOURCES.get(meta.get("source"), meta.get("source") or "unknown")
    if meta.get("run_url"):
        where = f"[{where} run]({meta['run_url']})"
    if meta.get("event"):
        where += f", on `{meta['event']}`" + (f" for PR #{meta['pr_number']}" if meta.get("pr_number") else "")
    if meta.get("by"):
        where += f", started by {meta['by']}"
    took = fmt_duration((tel.get("duration_ms") or 0) / 1000) if tel.get("duration_ms") else "–"
    if tel.get("num_turns") is not None:
        took += f" · {tel['num_turns']} turns"
    if tel.get("input_tokens") or tel.get("output_tokens"):
        took += f" · {tokens(tel.get('input_tokens'))} in / {tokens(tel.get('output_tokens'))} out tokens"
    took += f" · cost {'$%.2f' % tel['cost_usd'] if tel.get('cost_usd') is not None else 'not recorded'}"

    status = rec.get("status", "ok")
    status_text = {"ok": "Finished"}.get(status, status)
    if rec.get("stopped_at"):
        status_text += f" at `{rec['stopped_at']}`"
    if rec.get("reason") and status != "ok":
        status_text += f": {one_line(rec['reason'], 300)}"

    out = [f"# Agentic QE run — {when}", "",
           "| | |", "|---|---|",
           f"| Commit | `{rec.get('sha') or run.get('sha', '?')}` on `{rec.get('branch') or run.get('branch', '?')}` |",
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

    classes = [c for c in triage.get("classifications") or [] if isinstance(c, dict)]
    if classes:
        out += ["## How each failure was classified", "", "| Test | Verdict | Why |", "|---|---|---|"]
        out += [f"| {code(c.get('test', '?'), 80)} | {cell(c.get('type', '?'), 20)} | {cell(redact(c.get('reason', '')), 400)} |"
                for c in classes]
        out.append("")

    gh = rec.get("github") or {}
    filed = [i for i in gh.get("issues", []) if i.get("url")] + [p for p in gh.get("prs", []) if p.get("url")]
    if filed:
        out += ["## On GitHub", ""]
        for i in gh.get("issues", []):
            if i.get("url"):
                out.append(f"- Issue {i['url']} ({i['kind']})" + (f": {code(i['test'], 120)}" if i.get("test") else ""))
        for p in gh.get("prs", []):
            if p.get("url"):
                out.append(f"- PR {p['url']} ({p['kind']})" + (f": {one_line(p['summary'], 160)}" if p.get("summary") else ""))
        out.append("")

    drafts = [i for i in triage.get("issues_created") or [] if isinstance(i, dict) and i.get("report_only") and i.get("drafted_body")]
    if drafts:
        out += ["## Issues drafted but not filed (report-only)", ""]
        for i in drafts:
            out += [f"<details><summary>{code(i.get('test', '?'), 120)}: {cell(i.get('reason', ''), 160)}</summary>", "",
                    redact(i["drafted_body"].strip()), "", "</details>", ""]

    out += history_section(qa_runs, name)
    trace_where = (f"in the [run's artifacts]({meta['run_url']})" if meta.get("run_url")
                   else "in `.claude-pipeline/trace.md` on the machine that ran it")
    out += ["---", "",
            f"The full step-by-step trace isn't kept in the repo. It is {trace_where}. "
            f"Machine-readable record: [`{name}.json`]({name}.json).", ""]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pipeline-dir", default=".claude-pipeline")
    parser.add_argument("--qa-dir", default=".qa")
    parser.add_argument("--actor", default="", help="CI: who started the run (github.actor)")
    parser.add_argument("--event", default="", help="CI: what started it (github.event_name)")
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

    name = record_name(run)
    qa_runs = os.path.join(args.qa_dir, "runs")
    os.makedirs(qa_runs, exist_ok=True)

    rec = build_json(name, run, record, telemetry, github_activity(followup, triage), args)
    with open(os.path.join(qa_runs, f"{name}.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(rec, f, indent=2)
        f.write("\n")
    md = build_markdown(name, run, rec, triage, strip_summary(read_text(os.path.join(pdir, "summary.md"))), qa_runs)
    with open(os.path.join(qa_runs, f"{name}.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    readme = os.path.join(qa_runs, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8", newline="\n") as f:
            f.write(README)
    print(f"record_run: wrote {qa_runs}/{name}.md and .json")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- a missing record costs history, not the run
        print(f"record_run: {exc}", file=sys.stderr)
    sys.exit(0)
