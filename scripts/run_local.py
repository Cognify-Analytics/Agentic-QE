#!/usr/bin/env python3
"""Run the QA pipeline locally the way CI runs it, with the same telemetry
and the same summaries.

CI runs `/agentic-qe:test-pipeline` headless and gets a stream-json execution
log, from which it builds telemetry.json (cost, turns, tokens, stages), the
"run cost" block and the "what the agent did" timeline. This script does
exactly that on your machine: same command shape, same tool allowlist, same
scripts afterwards. Use it when you want the real cost of a local run. An
interactive /test-pipeline run in a Claude Code session also writes all of
these files, but session transcripts record tokens, not cost.

Usage (from the target repo's root):
    python <agentic-qe>/scripts/run_local.py [pipeline args...]
        [--max-turns 150] [--model NAME] [--plugin-dir <agentic-qe>]

    pipeline args are passed to /test-pipeline as typed: --live, --fix-bugs,
    --clickup-branches, a target file or folder.

Writes, in .claude-pipeline/:
    execution-log.json   the raw stream-json log (CI: the run artifact's copy)
    telemetry.json       the same schema CI uploads as qa-telemetry-*
    run-summary.md       what CI puts on the job summary page: run cost + timeline
    trace.md             the full step-by-step trace
    summary.md           the pipeline's own summary (CI: the PR comment)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = ".claude-pipeline"
ALLOWED_TOOLS = "Read,Write,Edit,Glob,Grep,Bash"  # the same allowlist the CI workflow passes


def progress(line):
    """One short line per tool call, so a long headless run isn't silent."""
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return
    if msg.get("type") != "assistant":
        return
    for block in (msg.get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            inp = block.get("input") or {}
            what = inp.get("skill") or inp.get("description") or inp.get("file_path") or inp.get("pattern") or ""
            stage = "  " if msg.get("parent_tool_use_id") else ""
            print(f"{stage}- {block.get('name')}: {str(what)[:100]}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--max-turns", type=int, default=150, help="same default as the CI workflow")
    parser.add_argument("--model", default="", help="leave empty for the CLI's default")
    parser.add_argument("--plugin-dir", default="", help="a local Agentic-QE checkout, instead of the installed plugin")
    args, pipeline_args = parser.parse_known_args()

    claude = shutil.which("claude")
    if not claude:
        print("run_local: the `claude` CLI isn't on PATH. Install Claude Code first.", file=sys.stderr)
        return 1

    os.makedirs(PIPELINE_DIR, exist_ok=True)
    log_path = os.path.join(PIPELINE_DIR, "execution-log.json")
    summary_path = os.path.join(PIPELINE_DIR, "run-summary.md")
    if os.path.exists(summary_path):
        os.remove(summary_path)

    prompt = " ".join(["/agentic-qe:test-pipeline", *pipeline_args]).strip()
    cmd = [claude, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--max-turns", str(args.max_turns), "--allowedTools", ALLOWED_TOOLS]
    if args.model:
        cmd += ["--model", args.model]
    if args.plugin_dir:
        cmd += ["--plugin-dir", args.plugin_dir]

    # Tells /test-pipeline not to build telemetry itself: this script does it
    # once the session has ended, from the complete log, cost included.
    env = dict(os.environ, AGENTIC_QE_TELEMETRY="external")
    print(f"Running: {prompt}  (headless, max {args.max_turns} turns)", flush=True)
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        for line in proc.stdout:
            log.write(line)
            progress(line)
        code = proc.wait()

    outcome = "success" if code == 0 else "failure"
    py = sys.executable
    subprocess.run([py, os.path.join(HERE, "collect_telemetry.py"), "--execution-file", log_path,
                    "--source", "local-headless", "--outcome", outcome, "--pipeline-dir", PIPELINE_DIR,
                    "--model", args.model or "cli-default", "--max-turns", str(args.max_turns),
                    "--summary", summary_path])
    subprocess.run([py, os.path.join(HERE, "render_trace.py"), log_path, "--pipeline-dir", PIPELINE_DIR,
                    "--summary", summary_path, "--out", os.path.join(PIPELINE_DIR, "trace.md")])

    print()
    for name in ("summary.md", "run-summary.md", "trace.md", "telemetry.json"):
        path = os.path.join(PIPELINE_DIR, name)
        print(f"  {'written' if os.path.exists(path) else 'missing'}: {path}")
    return 0 if code == 0 else code


if __name__ == "__main__":
    sys.exit(main())
