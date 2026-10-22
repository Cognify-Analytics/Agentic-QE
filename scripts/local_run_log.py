#!/usr/bin/env python3
"""Turn the part of a Claude Code session that ran /test-pipeline into an
execution log shaped like CI's.

In CI, claude-code-action hands the workflow an execution file: every
message of the run as stream-json, forked stages tagged with
`parent_tool_use_id`, and a final `result` message with turns, duration,
usage and cost. An interactive local run has no such file, but Claude Code
keeps a session transcript: one JSON line per message in
~/.claude/projects/<project>/<session>.jsonl, and one transcript per forked
stage or subagent in <session>/subagents/agent-*.jsonl (whose .meta.json
names the tool call that launched it).

This script cuts the run out of that transcript (from the prompt that
started /test-pipeline, found via run.json's timestamp, to now), merges the
forked stages back in with `parent_tool_use_id`, and ends it with a
`result` message, so scripts/render_trace.py and scripts/collect_telemetry.py
read it exactly as they read CI's. Transcripts carry token usage but not
cost: the result's total_cost_usd is null.

Usage:
    python scripts/local_run_log.py [--pipeline-dir .claude-pipeline]
        [--session PATH.jsonl] [--out .claude-pipeline/execution-log.json]

Without --session, the newest transcript of this project (the session that
is running the pipeline) is used. Never exits non-zero.
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def parse_ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def projects_root():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def project_dir(cwd):
    """Claude Code names a project's folder after its path, with every
    character that isn't a letter or digit replaced by '-'."""
    root = projects_root()
    name = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    exact = os.path.join(root, name)
    if os.path.isdir(exact):
        return exact
    if os.path.isdir(root):
        for entry in os.listdir(root):
            if entry.lower() == name.lower():
                return os.path.join(root, entry)
    return None


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    except OSError:
        pass
    return out


def text_of(entry):
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def run_start(entries, run_json):
    """The prompt that started this run: the last human prompt mentioning
    test-pipeline before run.json was written. run.json's own timestamp is
    the fallback."""
    written = parse_ts((run_json or {}).get("timestamp"))
    start = None
    for entry in entries:
        if entry.get("type") != "user" or entry.get("isSidechain"):
            continue
        ts = parse_ts(entry.get("timestamp"))
        if ts is None or (written and ts > written + timedelta(seconds=5)):
            continue
        if "test-pipeline" in text_of(entry):
            start = ts
    return start or written


def to_message(entry, parent_tool_use_id):
    msg = {
        "type": entry["type"],
        "message": entry.get("message"),
        "timestamp": entry.get("timestamp"),
        "parent_tool_use_id": parent_tool_use_id,
        "session_id": entry.get("sessionId"),
    }
    if "toolUseResult" in entry:
        msg["tool_use_result"] = entry["toolUseResult"]
    return msg


def tool_use_ids(entries):
    ids = set()
    for entry in entries:
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "assistant" and isinstance(content, list):
            ids.update(b.get("id") for b in content if isinstance(b, dict) and b.get("type") == "tool_use")
    return ids


def build_log(session_path, run_json):
    main = read_jsonl(session_path)
    start = run_start(main, run_json)

    def in_window(entry):
        ts = parse_ts(entry.get("timestamp"))
        return ts is not None and (start is None or ts >= start)

    main = [e for e in main if e.get("type") in ("user", "assistant") and in_window(e)]
    messages = [to_message(e, None) for e in main]
    known_ids = tool_use_ids(main)

    # Forked stages and subagents, nested ones included: keep adding any whose
    # launching tool call belongs to the run, until nothing new turns up.
    sub_dir = os.path.join(os.path.splitext(session_path)[0], "subagents")
    pending = {}
    for meta_path in glob.glob(os.path.join(sub_dir, "*.meta.json")):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        pending[meta_path[: -len(".meta.json")] + ".jsonl"] = meta.get("toolUseId")
    sub_entries_all = []
    added = True
    while added:
        added = False
        for path, parent in list(pending.items()):
            if parent in known_ids:
                entries = [e for e in read_jsonl(path) if e.get("type") in ("user", "assistant") and in_window(e)]
                messages += [to_message(e, parent) for e in entries]
                sub_entries_all += entries
                known_ids |= tool_use_ids(entries)
                del pending[path]
                added = True

    messages.sort(key=lambda m: parse_ts(m.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))

    # One API response is logged as several transcript lines (one per content
    # block) sharing a message id: count and sum each response once.
    usage, seen, turns, models = {k: 0 for k in USAGE_KEYS}, set(), set(), []
    for entry, is_main in [(e, True) for e in main] + [(e, False) for e in sub_entries_all]:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        key = message.get("id") or entry.get("requestId") or entry.get("uuid")
        if is_main:
            turns.add(key)
        if key in seen:
            continue
        seen.add(key)
        if message.get("model"):
            models.append(message["model"])
        for k in USAGE_KEYS:
            usage[k] += int((message.get("usage") or {}).get(k) or 0)

    stamps = [parse_ts(m.get("timestamp")) for m in messages if m.get("timestamp")]
    stamps = [s for s in stamps if s]
    duration_ms = int((max(stamps) - min(stamps)).total_seconds() * 1000) if len(stamps) > 1 else None
    first = next((e for e in main if e.get("cwd")), {})
    init = {"type": "system", "subtype": "init", "cwd": first.get("cwd") or os.getcwd(),
            "model": max(set(models), key=models.count) if models else None,
            "session_id": first.get("sessionId"), "source": "local-interactive"}
    result = {"type": "result", "subtype": "success", "is_error": False, "num_turns": len(turns),
              "duration_ms": duration_ms, "usage": usage, "total_cost_usd": None,
              "source": "local-interactive",
              "note": "built from the Claude Code session transcript; it records tokens, not cost"}
    return [init] + messages + [result]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pipeline-dir", default=".claude-pipeline")
    parser.add_argument("--session", help="the session transcript (.jsonl); default: this project's newest")
    parser.add_argument("--out", default=None, help="default: <pipeline-dir>/execution-log.json")
    args = parser.parse_args()
    out = args.out or os.path.join(args.pipeline_dir, "execution-log.json")

    session = args.session
    if not session:
        pdir = project_dir(os.getcwd())
        candidates = glob.glob(os.path.join(pdir, "*.jsonl")) if pdir else []
        session = max(candidates, key=os.path.getmtime) if candidates else None
    if not session or not os.path.isfile(session):
        print("local_run_log: no Claude Code session transcript found for this project "
              f"(looked in {projects_root()}); pass --session", file=sys.stderr)
        return

    try:
        with open(os.path.join(args.pipeline_dir, "run.json"), encoding="utf-8") as f:
            run_json = json.load(f)
    except (OSError, json.JSONDecodeError):
        run_json = None

    log = build_log(session, run_json)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for msg in log:
            f.write(json.dumps(msg) + "\n")
    print(f"local_run_log: {len(log) - 2} messages from {os.path.basename(session)} -> {out}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- telemetry must never fail a run
        print(f"local_run_log: {exc}", file=sys.stderr)
    sys.exit(0)
