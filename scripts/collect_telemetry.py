#!/usr/bin/env python3
"""Build a run's telemetry.json and its "run cost" summary block.

One implementation for every way the pipeline runs, so a CI run and a local
run produce the same file, with the same fields, worked out the same way:

    ci                 the GitHub Actions workflow, from the claude-code-action
                       execution file
    local-headless     scripts/run_local.py, from `claude -p --output-format
                       stream-json` output -- exact cost, same as CI
    local-interactive  /test-pipeline run inside a Claude Code session, from
                       the session transcript (scripts/local_run_log.py).
                       Transcripts record tokens but not cost, so cost_usd is
                       null and cost_source says why

Usage:
    python scripts/collect_telemetry.py --execution-file LOG --source ci|local-headless|local-interactive
        [--pipeline-dir .claude-pipeline] [--outcome success|failure|skipped|]
        [--repo org/repo] [--run-id ID] [--run-url URL] [--model NAME] [--effort LEVEL] [--max-turns N]
        [--summary FILE] [--github-output FILE] [--github]

Writes <pipeline-dir>/telemetry.json. --summary appends the "run cost" block
(the same Markdown the CI job summary shows); --github-output adds cost= and
turns= lines; --github prints the ::notice annotation. Never exits non-zero:
a missing or reshaped log costs a data point, not a run.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCHEMA_VERSION = 1


def load_messages(path):
    if not path or not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass
    messages = []
    for line in raw.splitlines():
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def last_result(node):
    """The last object anywhere in the log carrying total_cost_usd -- searched
    for rather than assumed at a fixed position, so a reshaped log still works."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            if "total_cost_usd" in value:
                found.append(value)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(node)
    return found[-1] if found else {}


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def git_repo():
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                             text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    url = url.removesuffix(".git")
    for sep in ("github.com:", "github.com/"):
        if sep in url:
            return url.split(sep, 1)[1]
    return None


def model_used(messages):
    for msg in messages:
        if isinstance(msg, dict) and msg.get("type") == "system" and msg.get("subtype") == "init" and msg.get("model"):
            return msg["model"]
    for msg in messages:
        model = isinstance(msg, dict) and (msg.get("message") or {}).get("model")
        if model:
            return model
    return None


def effort_used(messages):
    # Only the local-interactive log carries it (local_run_log.py copies it from
    # the transcript); a stream-json log doesn't, so CI and run_local.py pass --effort.
    for msg in messages:
        if isinstance(msg, dict) and msg.get("type") == "system" and msg.get("subtype") == "init" and msg.get("effort"):
            return msg["effort"]
    return None


def build(args):
    pdir = args.pipeline_dir
    run = load_json(os.path.join(pdir, "run.json")) or {}
    stages = load_json(os.path.join(pdir, "stages.json"))

    if args.outcome in ("", "skipped") and args.source == "ci":
        return {"schema_version": SCHEMA_VERSION, "source": args.source, "conclusion": "did-not-run"}

    messages = load_messages(args.execution_file)
    result = last_result(messages)
    ci = run.get("ci") or {}
    local = run.get("local") or {}

    conclusion = args.outcome
    if not conclusion:
        conclusion = "success" if result.get("subtype", "success") == "success" else "failure"

    cost = result.get("total_cost_usd")
    if cost is not None:
        cost_source = "reported"
    elif args.source == "local-interactive":
        cost_source = "not-recorded-in-session-transcript"
    else:
        cost_source = "missing-from-log"

    return {
        "schema_version": SCHEMA_VERSION,
        "source": args.source,
        "repo": args.repo or local.get("repo") or git_repo(),
        "run_id": args.run_id or f"local-{run.get('sha', 'unknown')}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
        "run_url": args.run_url or None,
        "conclusion": conclusion,
        "sha": run.get("sha"),
        "branch": run.get("branch"),
        "timestamp": run.get("timestamp"),
        "pr_number": ci.get("pr_number"),
        "strategy": ci.get("strategy") or ("local" if args.source != "ci" else None),
        "context_inputs_changed": ci.get("context_inputs_changed"),
        "live": run.get("live"),
        "fix_bugs": run.get("fix_bugs"),
        "model": args.model or model_used(messages) or "unknown",
        "model_used": model_used(messages),
        "effort": args.effort or effort_used(messages),
        "max_turns": args.max_turns,
        "cost_usd": cost,
        "cost_source": cost_source,
        "num_turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "usage": result.get("usage") or {},
        "stages": stages,
    }


def cost_block(telemetry):
    if telemetry.get("conclusion") == "did-not-run":
        return ("### Agentic QE\n\nThe pipeline did not run: a step before it failed — most often "
                "`setup_script` not matching the repo's layout. See the job log.\n")
    show = lambda v: "n/a" if v is None else v  # noqa: E731
    cost = telemetry.get("cost_usd")
    if cost is None and telemetry.get("cost_source") == "not-recorded-in-session-transcript":
        cost_text = "n/a (interactive session; use scripts/run_local.py for cost)"
    else:
        cost_text = show(cost)
    lines = [
        "### Agentic QE — run cost",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Cost (USD) | `{cost_text}` |",
        f"| Turns | `{show(telemetry.get('num_turns'))}` |",
        f"| Strategy | `{show(telemetry.get('strategy'))}` |",
        f"| Model | `{show(telemetry.get('model'))}` |",
        f"| Effort | `{show(telemetry.get('effort'))}` |",
        f"| Run | `{telemetry.get('source')}` |",
        "",
        "<details><summary>Full telemetry JSON</summary>",
        "",
        "```json",
        json.dumps(telemetry, indent=2),
        "```",
        "",
        "</details>",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--execution-file", default="")
    parser.add_argument("--source", required=True, choices=["ci", "local-headless", "local-interactive"])
    parser.add_argument("--pipeline-dir", default=".claude-pipeline")
    parser.add_argument("--outcome", default="", help="CI: steps.claude.outcome")
    parser.add_argument("--repo", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--model", default="", help="CI: the model input")
    parser.add_argument("--effort", default="", help="CI: the effort input")
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--summary", help="append the run-cost Markdown block here")
    parser.add_argument("--github-output", help="append cost= and turns= here ($GITHUB_OUTPUT)")
    parser.add_argument("--github", action="store_true", help="print the ::notice annotation")
    args = parser.parse_args()

    os.makedirs(args.pipeline_dir, exist_ok=True)
    try:
        telemetry = build(args)
    except Exception as exc:  # noqa: BLE001 -- telemetry must never fail a run
        telemetry = {"schema_version": SCHEMA_VERSION, "source": args.source,
                     "error": f"telemetry assembly failed: {exc}"}

    with open(os.path.join(args.pipeline_dir, "telemetry.json"), "w", encoding="utf-8") as f:
        json.dump(telemetry, f, indent=2)
        f.write("\n")
    # CI keeps each run's telemetry as a 90-day artifact. Locally, telemetry.json
    # is overwritten by the next run, so keep a copy per run for cost trends.
    if args.source != "ci" and telemetry.get("run_id"):
        history = os.path.join(args.pipeline_dir, "telemetry-history")
        os.makedirs(history, exist_ok=True)
        with open(os.path.join(history, f"{telemetry['run_id']}.json"), "w", encoding="utf-8") as f:
            json.dump(telemetry, f, indent=2)
            f.write("\n")

    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(cost_block(telemetry))

    cost = telemetry.get("cost_usd")
    turns = telemetry.get("num_turns")
    cost = "n/a" if cost is None else cost
    turns = "n/a" if turns is None else turns
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(f"cost={cost}\nturns={turns}\n")
    if telemetry.get("conclusion") == "did-not-run":
        print("The pipeline never ran — an earlier step failed. No telemetry to collect.")
    elif args.github:
        print(f"::notice title=Agentic QE cost::${cost} over {turns} turns (strategy: {telemetry.get('strategy') or 'n/a'})")
    else:
        print(f"Agentic QE telemetry: cost {cost} USD, {turns} turns -> "
              f"{os.path.join(args.pipeline_dir, 'telemetry.json')}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"collect_telemetry: {exc}", file=sys.stderr)
    sys.exit(0)
