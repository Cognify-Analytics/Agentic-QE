#!/usr/bin/env python3
"""Turn a Claude Code run log into a readable timeline of what the agent did.

The CI job log shows the run as raw SDK messages, one JSON blob per tool
call, which nobody can read. This script reads the same messages (the
claude-code-action `execution_file`, or `claude -p --output-format
stream-json --verbose` output) plus the pipeline's own scratch files, and
writes two Markdown documents:

- a short one for the job summary page: how the run ended, each stage's
  outcome and timing, what was skipped and why, the agent's decisions, any
  blocked or failed actions, and a collapsed step-by-step timeline per stage;
- a full one (--out) with every step, the agent's complete commentary, and
  each stage's final report, for the run artifact.

Stages are found from the Skill tool calls `/test-pipeline` makes. Forked
skills stream their own messages tagged with the launching call's
`parent_tool_use_id`, so every step is attributed to the stage it ran in.

Usage:
    python scripts/render_trace.py EXECUTION_FILE [--pipeline-dir .claude-pipeline]
        [--summary summary.md] [--out trace.md]

With neither --summary nor --out, the short version goes to stdout. Reads a
JSON array or JSON Lines. Never exits non-zero on bad input: a missing or
reshaped log costs the timeline, not the run.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

# Per-stage step cap on the summary page. GitHub caps a step summary at
# 1 MiB; the full trace in the artifact is never capped.
SUMMARY_STEP_LIMIT = 80

STAGE_KEYS = {
    "generate_tests": "generate-tests",
    "build_context": "build-context",
    "triage_tests": "triage-tests",
}

SKIP_REASONS = {
    "skipped:triage-only": "the PR changed no source files, so there was nothing to generate tests for",
    "skipped:inputs-unchanged": "no doc, manifest or schema file changed and Stage 1 changed nothing, so the context was still current",
    "not_reached": "the pipeline stopped before this stage",
}

RESULT_SUBTYPES = {
    "success": "✅ Finished",
    "error_max_turns": "❌ Stopped: hit the max-turns limit",
    "error_during_execution": "❌ Stopped: error during execution",
    "error_max_budget_usd": "❌ Stopped: hit the budget limit",
}

SECRET_PATTERNS = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._\-]{20,}"),
]


def redact(text):
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def one_line(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def code(text, limit=100):
    # Inline code can't contain a backtick; a pipe would split a table cell.
    return "`" + one_line(text, limit).replace("`", "'").replace("|", "¦") + "`"


def cell(text, limit=200):
    return one_line(text, limit).replace("|", "\\|")


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_duration(seconds):
    if seconds is None:
        return "–"
    seconds = int(round(seconds))
    if seconds >= 3600:
        return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m"
    return f"{seconds // 60}m {seconds % 60:02d}s"


def load_messages(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [m for m in data if isinstance(m, dict)]
        if isinstance(data, dict):
            return [data]
    except json.JSONDecodeError:
        pass
    messages = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            messages.append(obj)
    return messages


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


class Step:
    def __init__(self, kind, ts, text, tool_id=None, detail=None):
        self.kind = kind          # say | read | search | run | write | edit | skill | agent | tool
        self.ts = ts
        self.text = text          # short, one-line description
        self.tool_id = tool_id
        self.detail = detail      # longer text for the full trace
        self.status = None        # None | "error" | "blocked"
        self.problem = None
        self.paths = []           # for grouped reads


class Stage:
    """One Skill invocation: a pipeline stage."""

    def __init__(self, key, name):
        self.key = key
        self.name = name
        self.finished = None      # None = never returned, True = ok, False = failed
        self.report = None        # the stage's final message, from the Skill call's result


class Segment:
    """A contiguous stretch of the run spent in one place: a stage, or the
    orchestrator between stages."""

    def __init__(self, key, label, stage=None):
        self.key = key
        self.label = label
        self.stage = stage
        self.steps = []
        self.first_ts = None
        self.last_ts = None

    def touch(self, ts):
        if ts is None:
            return
        if self.first_ts is None or ts < self.first_ts:
            self.first_ts = ts
        if self.last_ts is None or ts > self.last_ts:
            self.last_ts = ts

    @property
    def seconds(self):
        if self.first_ts and self.last_ts:
            return (self.last_ts - self.first_ts).total_seconds()
        return None

    @property
    def problems(self):
        return [s for s in self.steps if s.status]


class Trace:
    def __init__(self, messages):
        self.cwd = ""
        self.result = None
        self.start_ts = None
        self.segments = []
        self.stages = {}          # Skill tool_use_id -> Stage, in launch order
        self.owner = {}           # tool_use_id -> key of the place its child messages belong to
        self.steps_by_tool = {}   # tool_use_id -> (Segment, Step)
        self._parse(messages)

    def rel(self, path):
        path = str(path).replace("\\", "/")
        cwd = self.cwd.replace("\\", "/").rstrip("/")
        if cwd and path.lower().startswith(cwd.lower() + "/"):
            return path[len(cwd) + 1:]
        return path

    def _segment_for(self, key):
        if self.segments and self.segments[-1].key == key:
            return self.segments[-1]
        if key == "main":
            prev = next((g.stage for g in reversed(self.segments) if g.stage), None)
            label = f"Orchestrator — after {prev.name}" if prev else "Orchestrator — setup"
            seg = Segment(key, label)
        else:
            stage = self.stages[key]
            seg = Segment(key, f"Stage — {stage.name}", stage)
        self.segments.append(seg)
        return seg

    def _parse(self, messages):
        for msg in messages:
            mtype = msg.get("type")
            if mtype == "system" and msg.get("subtype") == "init":
                self.cwd = msg.get("cwd") or self.cwd
                continue
            if mtype == "result":
                self.result = msg
                continue
            if mtype == "system" and msg.get("subtype") == "permission_denied":
                _, step = self.steps_by_tool.get(msg.get("tool_use_id"), (None, None))
                if step:
                    step.status = "blocked"
                    step.problem = redact(self.rel_text(msg.get("message") or msg.get("decision_reason") or "permission denied"))
                continue
            if mtype not in ("assistant", "user"):
                continue

            parent = msg.get("parent_tool_use_id")
            key = self.owner.get(parent, "main") if parent else "main"
            ts = parse_ts(msg.get("timestamp"))
            if ts and self.start_ts is None:
                self.start_ts = ts
            content = (msg.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue

            if mtype == "assistant":
                seg = self._segment_for(key)
                seg.touch(ts)
                for block in content:
                    self._assistant_block(block, seg, key, ts)
            else:
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        self._tool_result(block, msg, ts)

    def rel_text(self, text):
        cwd = self.cwd.replace("\\", "/").rstrip("/")
        text = str(text)
        if not cwd:
            return text
        for root in (self.cwd.rstrip("\\/"), cwd):
            text = text.replace(root + "\\", "").replace(root + "/", "").replace(root, ".")
        return text

    def _assistant_block(self, block, seg, key, ts):
        if not isinstance(block, dict):
            return
        btype = block.get("type")
        if btype == "text" and block.get("text", "").strip():
            text = redact(self.rel_text(block["text"].strip()))
            seg.steps.append(Step("say", ts, text, detail=text))
        elif btype == "tool_use":
            tool_id = block.get("id")
            name = block.get("name", "?")
            inp = block.get("input") or {}
            if name == "Skill":
                skill = str(inp.get("skill", "?")).split(":")[-1]
                self.stages[tool_id] = Stage(tool_id, skill)
                self.owner[tool_id] = tool_id
                step = Step("skill", ts, f"Started stage **{skill}**", tool_id)
            else:
                self.owner[tool_id] = key
                step = self._describe(name, inp, ts, tool_id)
            seg.steps.append(step)
            self.steps_by_tool[tool_id] = (seg, step)

    def _describe(self, name, inp, ts, tool_id):
        if name in ("Bash", "PowerShell"):
            cmd = redact(self.rel_text(inp.get("command", "")))
            desc = inp.get("description")
            text = f"{one_line(desc, 90)}: {code(cmd)}" if desc else code(cmd)
            return Step("run", ts, text, tool_id, detail=cmd)
        if name == "Read":
            step = Step("read", ts, "", tool_id)
            step.paths.append(self.rel(inp.get("file_path", "?")))
            return step
        if name == "Write":
            return Step("write", ts, f"Wrote {code(self.rel(inp.get('file_path', '?')))}", tool_id)
        if name in ("Edit", "MultiEdit", "NotebookEdit"):
            path = inp.get("file_path") or inp.get("notebook_path") or "?"
            return Step("edit", ts, f"Edited {code(self.rel(path))}", tool_id)
        if name == "Glob":
            return Step("search", ts, f"Looked for files matching {code(inp.get('pattern', '?'))}", tool_id)
        if name == "Grep":
            where = f" in {code(self.rel(inp['path']))}" if inp.get("path") else ""
            return Step("search", ts, f"Searched for {code(inp.get('pattern', '?'))}{where}", tool_id)
        if name in ("Task", "Agent"):
            return Step("agent", ts, f"Delegated to a subagent: {one_line(inp.get('description', ''), 100)}", tool_id)
        if name == "TodoWrite":
            todos = inp.get("todos") or []
            active = [t.get("content") or t.get("activeForm") for t in todos if t.get("status") == "in_progress"]
            text = f"Updated its plan ({len(todos)} items)" + (f", now on: {one_line(active[0], 80)}" if active else "")
            return Step("tool", ts, text, tool_id)
        summary = ", ".join(f"{k}={one_line(v, 40)}" for k, v in list(inp.items())[:3])
        return Step("tool", ts, f"Used {name}" + (f" ({summary})" if summary else ""), tool_id)

    def _tool_result(self, block, msg, ts):
        tool_id = block.get("tool_use_id")
        content = block.get("content")
        if isinstance(content, list):
            content = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
        content = redact(self.rel_text(content or ""))
        stage = self.stages.get(tool_id)
        if stage is not None:
            # The Skill call's own result: the stage is over, and this is its report.
            res = msg.get("tool_use_result")
            stage.finished = not block.get("is_error") and (not isinstance(res, dict) or res.get("success", True) is not False)
            report = res.get("result") if isinstance(res, dict) and res.get("result") else content
            stage.report = redact(self.rel_text(report))
            return
        seg, step = self.steps_by_tool.get(tool_id, (None, None))
        if step is None:
            return
        seg.touch(ts)
        if block.get("is_error") and step.status is None:
            step.status = "error"
            step.problem = one_line(content, 300)
        elif step.kind == "run" and content:
            step.detail = (step.detail or "") + "\n→ " + one_line(content, 300)


ICONS = {
    "say": "💬", "read": "📖", "search": "🔎", "run": "▶️", "write": "📝",
    "edit": "✏️", "skill": "🚩", "agent": "🤝", "tool": "🔧",
}


def group_reads(steps):
    """Collapse runs of consecutive file reads into one line."""
    out = []
    for step in steps:
        if (step.kind == "read" and not step.status and out and out[-1].kind == "read"
                and not out[-1].status):
            out[-1].paths.extend(step.paths)
            continue
        if step.kind == "read":
            merged = Step("read", step.ts, "", step.tool_id)
            merged.paths = list(step.paths)
            merged.status, merged.problem = step.status, step.problem
            out.append(merged)
        else:
            out.append(step)
    for step in out:
        if step.kind == "read":
            step.paths = list(dict.fromkeys(step.paths))
            shown = ", ".join(code(p, 80) for p in step.paths[:6])
            more = f" and {len(step.paths) - 6} more" if len(step.paths) > 6 else ""
            noun = "file" if len(step.paths) == 1 else f"{len(step.paths)} files"
            step.text = f"Read {noun}: {shown}{more}" if len(step.paths) > 1 else f"Read {shown}"
    return out


def render_step(step, start, full):
    offset = ""
    if step.ts and start:
        secs = int((step.ts - start).total_seconds())
        offset = f"`+{secs // 60:02d}:{secs % 60:02d}` "
    if step.kind == "say":
        if full:
            return f"- {offset}💬\n  > " + step.detail.replace("\n", "\n  > ")
        return f"- {offset}💬 {one_line(step.text, 400)}"
    line = f"- {offset}{ICONS.get(step.kind, '🔧')} {step.text}"
    if step.status == "blocked":
        line += f"\n  - ⛔ **Blocked:** {one_line(step.problem, 300)}"
    elif step.status == "error":
        line += f"\n  - ❌ **Failed:** {one_line(step.problem, 300)}"
    elif full and step.kind == "run" and step.detail and "\n→ " in step.detail:
        line += f"\n  - {one_line(step.detail.split(chr(10) + '→ ', 1)[1], 300)}"
    return line


def stage_rows(trace, stages_json):
    by_name = {st.name: st for st in trace.stages.values()}  # a re-run stage: its last run
    recorded = {STAGE_KEYS.get(k, k): v for k, v in (stages_json or {}).items()} if isinstance(stages_json, dict) else {}
    names = list(recorded) + [n for n in by_name if n not in recorded]
    rows = []
    for name in names:
        stage = by_name.get(name)
        if stage is not None:
            parts = [g for g in trace.segments if g.stage is stage]
            steps = sum(len([x for x in g.steps if x.kind != "say"]) for g in parts)
            problems = sum(len(g.problems) for g in parts)
            secs = sum(g.seconds or 0 for g in parts) or None
            if stage.finished is None:
                outcome = "⚠️ did not finish (the run ended mid-stage)"
            else:
                outcome = "✅ ran" if stage.finished else "❌ failed"
            rows.append((name, outcome, fmt_duration(secs), str(steps), str(problems)))
            continue
        value = recorded.get(name)
        if not isinstance(value, str):
            continue
        if value.startswith("skipped"):
            outcome = "⏭️ skipped — " + SKIP_REASONS.get(value, value.split(":", 1)[-1])
        elif value == "not_reached":
            outcome = "⛔ not reached — " + SKIP_REASONS["not_reached"]
        else:
            outcome = value
        rows.append((name, outcome, "–", "–", "–"))
    return rows


def skipped_section(stages_json, tests, triage):
    lines = []
    if isinstance(stages_json, dict):
        for key, value in stages_json.items():
            if isinstance(value, str) and value != "ran":
                reason = SKIP_REASONS.get(value, value)
                lines.append(f"- **Stage {STAGE_KEYS.get(key, key)}**: {reason}")
    if isinstance(tests, dict):
        for m in tests.get("modules_skipped") or []:
            if isinstance(m, dict):
                lines.append(f"- No tests written for {code(m.get('path', '?'))}: {one_line(m.get('reason', ''), 200)}")
        for t in tests.get("tests_removed") or []:
            if isinstance(t, dict):
                lines.append(f"- Discarded its own test {code(t.get('test', '?'))}: {one_line(t.get('reason', ''), 200)}")
    if isinstance(triage, dict):
        for e in triage.get("escalated") or []:
            if isinstance(e, dict):
                what = e.get("test") or e.get("file") or "?"
                lines.append(f"- Gave up on a fix for {code(what)}: {one_line(e.get('reason', ''), 200)}")
            else:
                lines.append(f"- Escalated: {one_line(e, 200)}")
        for c in triage.get("caps_hit") or []:
            lines.append(f"- Limit reached: {one_line(c if isinstance(c, str) else json.dumps(c), 200)}")
        if triage.get("branch_naming_problem"):
            lines.append(f"- No branch pushed: {one_line(triage['branch_naming_problem'], 200)}")
    return lines


def decisions_section(tests, triage):
    lines = []
    if isinstance(tests, dict):
        if tests.get("status") not in (None, "ok"):
            why = tests.get("reason") or tests.get("note") or tests.get("notes") or "no reason recorded"
            lines.append(f"**Test generation ended `{tests.get('status')}`:** {one_line(why, 300)}")
            lines.append("")
        created = tests.get("files_created") or []
        modified = tests.get("files_modified") or []
        if created or modified:
            files = ", ".join(code(f, 80) for f in (created + modified)[:10])
            if len(created + modified) > 10:
                files += f" and {len(created + modified) - 10} more"
            lines.append(f"**Tests written:** {len(created)} new file(s), {len(modified)} changed: {files}")
            lines.append("")
        flagged = tests.get("tests_flagged_as_possible_bugs") or []
        if flagged:
            lines.append("**Tests it kept failing on purpose, as possible bugs:**")
            for t in flagged:
                if isinstance(t, dict):
                    lines.append(f"- {code(t.get('test', '?'))}: {one_line(t.get('reason', ''), 250)}")
            lines.append("")
    if isinstance(triage, dict):
        if triage.get("status") not in (None, "ok"):
            lines.append(f"**Triage ended `{triage.get('status')}`:** {one_line(triage.get('reason', 'no reason recorded'), 300)}")
            lines.append("")
        totals = triage.get("totals") or {}
        if totals:
            lines.append(f"**Test run:** {totals.get('tests', '?')} tests, {totals.get('passed', '?')} passed, {totals.get('failed', '?')} failed")
            lines.append("")
        classes = triage.get("classifications") or []
        if classes:
            lines.append("**How each failure was classified:**")
            lines.append("")
            lines.append("| Test | Verdict | Why |")
            lines.append("|---|---|---|")
            for c in classes[:30]:
                if isinstance(c, dict):
                    lines.append(f"| {code(c.get('test', '?'), 70)} | {cell(c.get('type', '?'), 20)} | {cell(c.get('reason', ''), 250)} |")
            if len(classes) > 30:
                lines.append(f"| … | | {len(classes) - 30} more in `03-triage.json` |")
            lines.append("")
        fixes = triage.get("fixes_applied") or []
        if fixes:
            lines.append("**Fixes it made:**")
            for f in fixes:
                if isinstance(f, dict):
                    tries = f.get("attempts")
                    lines.append(f"- {code(f.get('test', '?'))}: {one_line(f.get('change', ''), 200)}" + (f" ({tries} attempt(s))" if tries else ""))
            lines.append("")
        for b in triage.get("bug_fix_prs_created") or []:
            if isinstance(b, dict):
                lines.append(f"- **Bug fix** in {code(b.get('file_changed', '?'))}: {one_line(b.get('summary', ''), 200)}")
    return lines


def render(trace, stages_json, tests, triage, full):
    out = ["### Agentic QE — what the agent did", ""]
    res = trace.result or {}
    if res:
        subtype = res.get("subtype", "")
        head = RESULT_SUBTYPES.get(subtype, f"Ended: `{subtype or 'unknown'}`")
        bits = [head]
        if res.get("num_turns") is not None:
            bits.append(f"{res['num_turns']} turns")
        if res.get("duration_ms") is not None:
            bits.append(fmt_duration(res["duration_ms"] / 1000))
        out.append(" · ".join(bits))
    elif trace.segments:
        out.append("⚠️ The log has no final result: the run was cut off before it finished (timeout or cancellation).")
    else:
        out.append("⚠️ The execution log was empty or unreadable, so there is no timeline for this run.")
    out.append("")

    rows = stage_rows(trace, stages_json)
    if rows:
        out += ["| Stage | Outcome | Time | Steps | Problems |", "|---|---|---|---|---|"]
        out += [f"| {r[0]} | {cell(r[1], 200)} | {r[2]} | {r[3]} | {r[4]} |" for r in rows]
        out.append("")

    skipped = skipped_section(stages_json, tests, triage)
    if skipped:
        out += ["#### Skipped, and why", ""] + skipped[:8] + [""]
        if len(skipped) > 8:
            out += [f"<details><summary>{len(skipped) - 8} more</summary>", ""] + skipped[8:] + ["", "</details>", ""]

    decisions = decisions_section(tests, triage)
    if decisions:
        out += ["#### Decisions", ""] + decisions + [""]

    problems = [(seg, s) for seg in trace.segments for s in seg.problems]
    if problems:
        out += ["#### Blocked or failed actions", ""]
        for seg, s in problems[:25]:
            mark = "⛔ blocked" if s.status == "blocked" else "❌ failed"
            out.append(f"- *{seg.label}* — {s.text or ('Read ' + ', '.join(s.paths))}: {mark}: {one_line(s.problem, 250)}")
        if len(problems) > 25:
            out.append(f"- …and {len(problems) - 25} more (see the full trace)")
        out += ["", "<sub>A failed step is not always a problem: the agent often tries something, sees it fail, and adapts.</sub>", ""]

    if trace.segments:
        out += ["#### Step by step", ""]
        for seg in trace.segments:
            steps = group_reads(seg.steps)
            last_of_stage = seg.stage and seg is [g for g in trace.segments if g.stage is seg.stage][-1]
            report = seg.stage.report if last_of_stage else None
            # A forked stage's closing message is also its report; show it once.
            if report and steps and steps[-1].kind == "say" and " ".join(steps[-1].text.split()) == " ".join(report.split()):
                steps = steps[:-1]
            if not steps and not report:
                continue
            actions = len([s for s in seg.steps if s.kind != "say"])
            summary = f"{seg.label} ({actions} steps, {fmt_duration(seg.seconds)})"
            shown = steps if full else steps[:SUMMARY_STEP_LIMIT]
            if full:
                out += [f"##### {summary}", ""]
            else:
                out += [f"<details><summary>{summary}</summary>", ""]
            out += [render_step(s, trace.start_ts, full) for s in shown]
            if len(steps) > len(shown):
                out.append(f"- …{len(steps) - len(shown)} more steps in `trace.md` (run artifact)")
            if report:
                quoted = report.replace("\n", "\n> ") if full else one_line(report, 1500)
                out +=["", "**Stage report:**", "", "> " + quoted]
            out.append("")
            if not full:
                out += ["</details>", ""]
    if not full:
        out.append("<sub>Full step-by-step trace, with the agent's complete commentary: `trace.md` in the run's `qa-pipeline-*` artifact.</sub>")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("execution_file")
    parser.add_argument("--pipeline-dir", default=".claude-pipeline")
    parser.add_argument("--summary", help="write the short version here (e.g. $GITHUB_STEP_SUMMARY, appended)")
    parser.add_argument("--out", help="write the full trace here")
    args = parser.parse_args()

    try:
        messages = load_messages(args.execution_file)
    except OSError as exc:
        messages = []
        print(f"render_trace: could not read {args.execution_file}: {exc}", file=sys.stderr)

    trace = Trace(messages)
    pdir = args.pipeline_dir
    stages_json = load_json(os.path.join(pdir, "stages.json"))
    tests = load_json(os.path.join(pdir, "01-tests.json"))
    triage = load_json(os.path.join(pdir, "03-triage.json"))

    short = render(trace, stages_json, tests, triage, full=False)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(short)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(render(trace, stages_json, tests, triage, full=True))
    if not args.summary and not args.out:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(short)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — a broken timeline must never fail the job
        print(f"render_trace: could not build the timeline: {exc}", file=sys.stderr)
    sys.exit(0)
