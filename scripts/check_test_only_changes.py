#!/usr/bin/env python3
"""Check that a pipeline run changed only tests and its own bookkeeping.

The CI workflow runs this twice: once with --snapshot just before the model
starts, and once with --baseline after it has finished. Only paths that are
changed *now*, and were not already changed with the same content before the
run, are judged -- so a setup_script that rewrites a lock file is not blamed
on the pipeline.

Usage:
    python scripts/check_test_only_changes.py --snapshot <file>
    python scripts/check_test_only_changes.py [--baseline <file>] [--github]

Every changed path (tracked or untracked, from `git status`) lands in one
of four groups:

    pipeline    .qa/ and .claude-pipeline/ -- the pipeline's own output
    test        a test file, recognised by where it lives or what it is called
    byproduct   something a test run leaves behind: coverage reports, caches,
                virtualenvs. Untracked files only. Reported, never failed,
                and never committed -- the workflow only ever commits .qa/
    other       everything else: production source, config, lock files

Any "other" path fails the check (exit 1); otherwise it exits 0.

Tests are recognised by convention, never by what the run says it wrote --
a safety check that trusted the model's own report would check nothing:

    a directory named like tests/, test/, spec/, __tests__/, e2e/, cypress/,
    __snapshots__/, src/test/..., MyApp.Tests/, integration_tests/, or a
    Gradle test source set straight under src/ (src/testFixtures/,
    src/jvmTest/, src/integrationTest/)
    a file named like test_x.py, x_test.py, conftest.py, x.test.ts,
    x.spec.js, x_test.go, FooTest.java, FooTests.cs, x_spec.rb, FooTest.php,
    setupTests.ts, vitest.setup.ts, test-utils.tsx

So a co-located test (frontend/src/lib/format.test.ts) passes, while
frontend/src/lib/format.ts right next to it does not.

--github adds workflow annotations: an error that names every offending
file, and notices for what was ignored.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

PIPELINE_DIRS = (".qa/", ".claude-pipeline/")

# Matched against each directory in a path, never the file name.
TEST_DIR = re.compile(
    r"^(?:__tests__|__mocks__|__snapshots__|e2e|cypress)$"
    r"|(?:^|[._-])(?:tests?|specs?|testing)(?:$|[._-])",
    re.IGNORECASE,
)
# A Gradle source set directly under src/. Case-sensitive and anchored to
# src/ on purpose: a feature folder like src/features/abTest/ is production.
TEST_SOURCE_SET = re.compile(r"^(?:testFixtures|[a-z][A-Za-z]*Test)$")
# Matched against the file name.
TEST_FILE = re.compile(
    r"^(?:test_.+\.py|.+_test\.py|conftest\.py"
    r"|.+\.(?:test|spec)\.[cm]?[jt]sx?"
    r"|.+_test\.go"
    r"|.+(?:Test|Tests|IT|Spec)\.(?:java|kt|kts|scala|groovy|cs|swift)"
    r"|.+_(?:spec|test)\.rb"
    r"|.+Test\.php"
    r"|(?:setupTests|setup-tests|jest\.setup|vitest\.setup)\.[cm]?[jt]sx?"
    r"|(?:test-utils|testUtils|test-helpers|testHelpers)\.[cm]?[jt]sx?)$"
)

# What running a test suite leaves behind. Only ever applied to untracked
# paths, and a directory only counts if git tracks nothing inside it -- so a
# real source package that happens to be called coverage/ is still judged.
# target/ and build/ are Maven's and Gradle's output: a repo that forgot to
# gitignore them would otherwise fail every Java/Kotlin run.
BYPRODUCT_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".hypothesis", "htmlcov",
    "coverage", ".nyc_output", "test-results", "playwright-report",
    ".next", ".swc", ".turbo", "target", "build", ".gradle", ".kotlin",
}
BYPRODUCT_FILE = re.compile(
    r"^(?:\.coverage(?:\..+)?|coverage\.(?:xml|json|lcov)"
    r"|coverage-(?:final|summary)\.json|cobertura-coverage\.xml|clover\.xml"
    r"|lcov\.info|junit(?:-.+)?\.xml|test-results\.xml|.+\.py[co]|\.DS_Store"
    r"|jacoco.*\.exec|.+\.tsbuildinfo)$"
)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def changed_paths():
    """{path: two-letter git status} for every changed path, untracked included."""
    out = git("status", "--porcelain=v1", "-z", "--untracked-files=all").decode("utf-8", "surrogateescape")
    entries = out.split("\0")
    changed = {}
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        changed[path] = status
        # A rename or copy is followed by its source path. A renamed file is
        # gone from its old path, which is a change to that path too.
        if "R" in status or "C" in status:
            source = entries[i]
            i += 1
            if "R" in status:
                changed.setdefault(source, "D ")
    return changed


def fingerprint(path):
    if os.path.islink(path):
        return "link:" + os.readlink(path)
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    return "present" if os.path.exists(path) else "missing"


def tracked_dirs():
    dirs = set()
    for path in git("ls-files", "-z").decode("utf-8", "surrogateescape").split("\0"):
        parts = path.split("/")[:-1]
        for n in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:n]))
    return dirs


def is_byproduct(parts, tracked):
    if BYPRODUCT_FILE.match(parts[-1]):
        return True
    for n, part in enumerate(parts[:-1], start=1):
        if part in BYPRODUCT_DIRS and "/".join(parts[:n]) not in tracked():
            return True
    return False


def classify(path, untracked, tracked):
    if path.startswith(PIPELINE_DIRS):
        return "pipeline"
    parts = path.split("/")
    if untracked and is_byproduct(parts, tracked):
        return "byproduct"
    if (any(TEST_DIR.search(part) for part in parts[:-1])
            or any(parts[n - 1] == "src" and TEST_SOURCE_SET.match(parts[n])
                   for n in range(1, len(parts) - 1))
            or TEST_FILE.match(parts[-1])):
        return "test"
    return "other"


def annotate(level, title, lines):
    # Workflow commands need %, CR and LF escaped to keep a multi-line message.
    message = "\n".join(lines).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{level} title={title}::{message}")


def check(baseline, github):
    changed = changed_paths()
    groups = {"pipeline": [], "test": [], "byproduct": [], "other": []}
    preexisting = []
    cache = {}

    def tracked():
        if "dirs" not in cache:
            cache["dirs"] = tracked_dirs()
        return cache["dirs"]

    for path, status in sorted(changed.items()):
        if path in baseline and baseline[path] == fingerprint(path):
            preexisting.append(path)
            continue
        groups[classify(path, status == "??", tracked)].append(path)

    print(f"{len(changed)} changed path(s) checked.")
    for name, label in (("pipeline", "Pipeline output (.qa/, .claude-pipeline/)"),
                        ("test", "Test files"),
                        ("byproduct", "Test-run by-products (ignored, never committed)")):
        print(f"  {label}: {len(groups[name])}")
        for path in groups[name]:
            print(f"    {path}")
    if preexisting:
        print(f"  Already changed before the run started (not judged): {len(preexisting)}")
        for path in preexisting:
            print(f"    {path}")

    if github and groups["byproduct"]:
        annotate("notice", "Agentic QE safety check",
                 [f"Ignored {len(groups['byproduct'])} file(s) the test run left behind:", *groups["byproduct"]])
    if github and preexisting:
        annotate("notice", "Agentic QE safety check",
                 [f"Not judged: {len(preexisting)} file(s) were already changed before the pipeline ran "
                  "(usually by setup_script):", *preexisting])

    if groups["other"]:
        print(f"  NOT ALLOWED -- changed outside tests: {len(groups['other'])}")
        for path in groups["other"]:
            print(f"    {path}")
        if github:
            annotate("error", "Agentic QE safety check",
                     [f"The pipeline changed {len(groups['other'])} file(s) that are not tests or its own output:",
                      *groups["other"],
                      "If one of these is really a test, its name or folder doesn't follow a common test "
                      "convention -- see scripts/check_test_only_changes.py."])
        return 1
    print("OK: only tests and pipeline output changed.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--snapshot", metavar="FILE", help="record what is already changed, then exit")
    mode.add_argument("--baseline", metavar="FILE", help="a --snapshot file from before the run")
    parser.add_argument("--github", action="store_true", help="emit GitHub Actions annotations")
    args = parser.parse_args()

    if args.snapshot:
        snapshot = {path: fingerprint(path) for path in changed_paths()}
        with open(args.snapshot, "w") as f:
            json.dump(snapshot, f, indent=2, sort_keys=True)
        print(f"Snapshot: {len(snapshot)} path(s) already changed before the run.")
        return 0

    baseline = {}
    if args.baseline:
        try:
            with open(args.baseline) as f:
                baseline = json.load(f)
        except (OSError, ValueError) as e:
            print(f"No usable snapshot ({e}); judging every change.")
    return check(baseline, args.github)


if __name__ == "__main__":
    sys.exit(main())
