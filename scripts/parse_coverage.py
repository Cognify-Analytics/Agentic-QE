#!/usr/bin/env python3
"""Parse coverage reports into the clean JSON shape skills need for
.qa/test-inventory.json's "coverage" fields.

Three formats are read, detected from the file itself:

    Cobertura XML   pytest-cov (--cov-report=xml), Jest/Vitest's "cobertura"
                    reporter, and coverage tooling for several other stacks
    JaCoCo XML      Maven/Gradle's jacoco plugin, and Kotlin's Kover
                    (koverXmlReport writes the same format)
    LCOV            Jest/Vitest's default lcov.info, c8, node --test

Usage:
    python scripts/parse_coverage.py [report ...] [--project-dir DIR]
                                     [--source-root DIR ...] [--out out.json]

With no report, the first one found at DEFAULT_REPORTS under --project-dir
is read. Several reports -- one per Maven/Gradle module, say -- are merged
into one result, the total weighted by line count. Prints JSON to stdout:

    {
      "total": 67.4,
      "format": "cobertura",
      "measured_at": "coverage.xml",
      "files": [
        {"path": "src/orders.py", "coverage": 82.1},
        {"path": "src/users.py", "coverage": 45.2}
      ]
    }

Every "path" is relative to --project-dir (default: the current directory),
so run this from the directory .qa/test-inventory.json's "source" paths are
relative to -- the repo root. Each tool records paths relative to its own
root, so a path is resolved by checking which candidate actually exists on
disk. JaCoCo only records Java/Kotlin files by package ("com/acme/Order.java");
their source root is found under src/main/java, src/main/kotlin, the
module the report sits in, and any --source-root given.
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

DEFAULT_REPORTS = (
    "coverage.xml",                                    # pytest-cov
    "coverage/cobertura-coverage.xml",                 # Jest / Vitest, cobertura reporter
    "coverage/lcov.info",                              # Jest / Vitest default, c8
    "lcov.info",                                       # node --test, lcov reporter
    "target/site/jacoco/jacoco.xml",                   # Maven + jacoco
    "build/reports/jacoco/test/jacocoTestReport.xml",  # Gradle + jacoco
    "build/reports/kover/report.xml",                  # Gradle + Kover
)

JVM_SOURCE_ROOTS = ("src/main/java", "src/main/kotlin")

# A directory holding one of these is a project/module root: the place a
# tool's own relative paths usually start from.
MANIFESTS = (
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts",
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
)


def _norm(path):
    return path.replace("\\", "/")


def _join(*parts):
    return "/".join(p.strip("/") for p in parts if p and p.strip("/"))


def _rel_to_project(path, project_dir):
    """Path relative to project_dir, or None if it lies outside it."""
    path = _norm(path).rstrip("/")
    if not os.path.isabs(path):
        return path
    try:
        rel = _norm(os.path.relpath(path, project_dir))
    except ValueError:  # another drive, on Windows
        return None
    if rel == ".." or rel.startswith("../"):
        return None
    return "" if rel == "." else rel


def _report_root(report_path, project_dir):
    """The nearest directory above the report that holds a manifest --
    e.g. frontend/ for frontend/coverage/lcov.info. "" for project_dir."""
    project = os.path.abspath(project_dir)
    current = os.path.dirname(os.path.abspath(report_path))
    while current.startswith(project) and current != project:
        if any(os.path.isfile(os.path.join(current, m)) for m in MANIFESTS):
            return _rel_to_project(current, project) or ""
        current = os.path.dirname(current)
    return ""


def _pick(candidates, project_dir, default=None):
    """The first candidate that exists under project_dir, else default (or
    the first candidate)."""
    for candidate in candidates:
        if os.path.isfile(os.path.join(project_dir, candidate)):
            return candidate
    return candidates[0] if default is None else default


def _percent(covered, total):
    return round(covered / total * 100, 1) if total else 0.0


# Each parser returns (covered_lines, total_lines, files). Line counts, not
# a percentage, so that several reports can be merged with the right weight.

def parse_cobertura(root, project_dir, report_root):
    # Cobertura records filenames relative to a <source> root -- "orders.py"
    # under /repo/src for pytest-cov --cov=src, "src/lib/auth.ts" under
    # /repo for Istanbul (Jest/Vitest).
    prefixes = []
    fallback = ""
    for source_el in root.findall("./sources/source"):
        if not source_el.text or not source_el.text.strip():
            continue
        source = _norm(source_el.text.strip()).rstrip("/")
        rel = _rel_to_project(source, project_dir)
        if rel is not None:
            prefixes.append(rel)
            if not os.path.isabs(source):
                prefixes.append(_join(report_root, rel))
        # Made on another machine: keep the last component (pytest-cov's
        # --cov=src gives "src"), which is what this script always did.
        last = source.rsplit("/", 1)[-1]
        prefixes.append(last)
        fallback = fallback or last
    prefixes += [report_root, ""]

    files = []
    for cls in root.iter("class"):
        filename = cls.attrib.get("filename")
        line_rate = cls.attrib.get("line-rate")
        if filename is None or line_rate is None:
            continue
        filename = _norm(filename)
        path = _pick([_join(p, filename) for p in prefixes], project_dir,
                     default=_join(fallback, filename))
        files.append({"path": path, "coverage": round(float(line_rate) * 100, 1)})

    covered, valid = root.attrib.get("lines-covered"), root.attrib.get("lines-valid")
    if covered is not None and valid is not None:
        return int(covered), int(valid), files
    # No counts: a single report's total is still exact; a merge weights it as one line.
    return float(root.attrib.get("line-rate", 0.0)), 1.0, files


def _line_counter(element):
    for counter in element.findall("counter"):
        if counter.attrib.get("type") == "LINE":
            return int(counter.attrib.get("covered", 0)), int(counter.attrib.get("missed", 0))
    return None


def parse_jacoco(root, project_dir, report_root, source_roots):
    files = []

    def visit(node, groups):
        for child in node:
            if child.tag == "group":
                visit(child, groups + [child.attrib.get("name", "")])
            elif child.tag == "package":
                package = child.attrib.get("name", "")
                for sourcefile in child.findall("sourcefile"):
                    name = sourcefile.attrib.get("name")
                    counter = _line_counter(sourcefile)
                    if name is None or counter is None or sum(counter) == 0:
                        continue
                    rel = _join(package, name)
                    default_root = "src/main/kotlin" if name.endswith(".kt") else "src/main/java"
                    # An aggregate report names each module's <group> after it,
                    # which is usually also the module's folder.
                    modules = [report_root] + ([groups[-1]] if groups else [])
                    candidates = [_join(m, default_root, rel) for m in modules]
                    for module in modules:
                        for base in (*source_roots, *JVM_SOURCE_ROOTS):
                            candidates.append(_join(module, base, rel))
                    candidates.append(rel)
                    covered, missed = counter
                    files.append({"path": _pick(candidates, project_dir),
                                  "coverage": _percent(covered, covered + missed)})

    visit(root, [])
    covered, missed = _line_counter(root) or (0, 0)
    return covered, covered + missed, files


def parse_lcov(text, project_dir, report_root):
    files = []
    hit_total = found_total = 0
    path = None
    found = hit = None
    da_found = da_hit = 0
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SF:"):
            path, found, hit, da_found, da_hit = line[3:], None, None, 0, 0
        elif line.startswith("DA:"):
            da_found += 1
            parts = line[3:].split(",")
            if len(parts) > 1 and parts[1].strip() not in ("", "0"):
                da_hit += 1
        elif line.startswith("LF:"):
            found = int(line[3:])
        elif line.startswith("LH:"):
            hit = int(line[3:])
        elif line == "end_of_record" and path is not None:
            found = da_found if found is None else found
            hit = da_hit if hit is None else hit
            if found:
                rel = _rel_to_project(path, project_dir)
                candidates = [rel] if rel is not None and os.path.isabs(_norm(path)) else []
                candidates += [_join(report_root, _norm(path)), _norm(path)]
                files.append({"path": _pick(candidates, project_dir),
                              "coverage": _percent(hit, found)})
                hit_total += hit
                found_total += found
            path = None
    return hit_total, found_total, files


def parse_report(report_path, project_dir=".", source_roots=()):
    """(format, covered_lines, total_lines, files) for one report."""
    report_root = _report_root(report_path, project_dir)
    with open(report_path, "rb") as f:
        head = f.read(4096).lstrip()

    if head.startswith(b"<"):
        root = ET.parse(report_path).getroot()
        if root.tag == "coverage":
            return ("cobertura", *parse_cobertura(root, project_dir, report_root))
        if root.tag == "report":
            return ("jacoco", *parse_jacoco(root, project_dir, report_root, source_roots))
        raise ValueError(f"unrecognised coverage XML (root element <{root.tag}>); "
                         "expected Cobertura <coverage> or JaCoCo <report>")

    with open(report_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if "SF:" not in text:
        raise ValueError("not a Cobertura, JaCoCo or LCOV coverage report")
    return ("lcov", *parse_lcov(text, project_dir, report_root))


def parse_reports(report_paths, project_dir=".", source_roots=()):
    formats, covered, total, files = [], 0, 0, []
    for report_path in report_paths:
        fmt, report_covered, report_total, report_files = parse_report(
            report_path, project_dir, source_roots)
        formats.append(fmt)
        covered += report_covered
        total += report_total
        files += report_files

    # A report can list the same file more than once (Cobertura across
    # packages, JaCoCo across groups); keep the highest figure for each path.
    by_path = {}
    for entry in files:
        existing = by_path.get(entry["path"])
        if existing is None or entry["coverage"] > existing["coverage"]:
            by_path[entry["path"]] = entry

    return {
        "total": _percent(covered, total),
        "format": formats[0] if len(set(formats)) == 1 else "mixed",
        "files": sorted(by_path.values(), key=lambda f: f["path"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "report_paths", nargs="*", metavar="report",
        help="Cobertura XML, JaCoCo XML or LCOV report(s) (default: first of DEFAULT_REPORTS found)",
    )
    parser.add_argument(
        "--project-dir", default=".",
        help="directory output paths are relative to -- the repo root (default: .)",
    )
    parser.add_argument(
        "--source-root", action="append", default=[],
        help="JaCoCo only: an extra source root to look for package paths under, "
             "e.g. app/src/main/java (repeatable)",
    )
    parser.add_argument(
        "--out", default=None,
        help="write JSON to this file instead of stdout",
    )
    args = parser.parse_args()

    report_paths = args.report_paths
    if not report_paths:
        found = [p for p in DEFAULT_REPORTS if os.path.isfile(os.path.join(args.project_dir, p))]
        if not found:
            print(json.dumps({"error": "no coverage report found; looked for "
                              + ", ".join(DEFAULT_REPORTS)}), file=sys.stderr)
            sys.exit(1)
        report_paths = [os.path.normpath(os.path.join(args.project_dir, found[0]))]

    try:
        result = parse_reports(report_paths, args.project_dir, args.source_root)
    except FileNotFoundError as exc:
        print(
            json.dumps({"error": f"coverage file not found: {exc.filename}"}),
            file=sys.stderr,
        )
        sys.exit(1)
    except (ET.ParseError, ValueError) as exc:
        print(
            json.dumps({"error": f"could not parse {', '.join(report_paths)}: {exc}"}),
            file=sys.stderr,
        )
        sys.exit(1)

    result["measured_at"] = ", ".join(
        _rel_to_project(p, args.project_dir) or _norm(p) for p in report_paths)
    output = json.dumps(result, indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
