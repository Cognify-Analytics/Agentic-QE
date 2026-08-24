#!/usr/bin/env python3
"""Resolve a file path to an owner via CODEOWNERS.

Looks for CODEOWNERS in the conventional locations (repo root, .github/,
docs/) and matches the given path against its patterns, last match wins
(matching GitHub's own CODEOWNERS precedence rule).

Usage:
    python scripts/resolve_owners.py <path/to/file> [--repo-root .]

Prints JSON to stdout:

    {"path": "src/pricing.py", "owners": ["@payments-team"], "source": "CODEOWNERS"}

If no CODEOWNERS file exists, or nothing matches, "owners" is an empty list
and "source" explains why -- this is not an error, it's a normal outcome
that /triage-tests must handle by filing the issue without an assignee
rather than guessing or crashing.
"""

import argparse
import fnmatch
import json
import os
import sys

CODEOWNERS_LOCATIONS = ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"]


def find_codeowners(repo_root):
    for rel_path in CODEOWNERS_LOCATIONS:
        candidate = os.path.join(repo_root, rel_path)
        if os.path.isfile(candidate):
            return candidate
    return None


def parse_codeowners(codeowners_path):
    """Return a list of (pattern, [owners]) in file order."""
    rules = []
    with open(codeowners_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            pattern, owners = parts[0], parts[1:]
            rules.append((pattern, owners))
    return rules


def _pattern_matches(pattern, path):
    # CODEOWNERS patterns are gitignore-style. This handles the common
    # cases (exact path, *.ext, a directory prefix ending in /or/**) without
    # pulling in a full gitignore-matching dependency.
    normalized = path.replace("\\", "/")
    pat = pattern.lstrip("/")

    if pat.endswith("/**"):
        prefix = pat[: -len("/**")]
        return normalized == prefix or normalized.startswith(prefix + "/")
    if pat.endswith("/"):
        return normalized.startswith(pat)
    return fnmatch.fnmatch(normalized, pat) or fnmatch.fnmatch(
        normalized, pat.rstrip("/") + "/*"
    )


def resolve_owners(path, repo_root="."):
    codeowners_path = find_codeowners(repo_root)
    if codeowners_path is None:
        return {
            "path": path,
            "owners": [],
            "source": "no CODEOWNERS file found in repo root, .github/, or docs/",
        }

    rules = parse_codeowners(codeowners_path)
    matched_owners = []
    matched_pattern = None
    for pattern, owners in rules:
        if _pattern_matches(pattern, path):
            matched_owners = owners
            matched_pattern = pattern

    if matched_pattern is None:
        return {
            "path": path,
            "owners": [],
            "source": f"CODEOWNERS found at {codeowners_path}, but no rule matched {path}",
        }

    return {
        "path": path,
        "owners": matched_owners,
        "source": f"CODEOWNERS:{matched_pattern}",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="repo-relative path to resolve an owner for")
    parser.add_argument("--repo-root", default=".", help="repo root to search for CODEOWNERS")
    args = parser.parse_args()

    result = resolve_owners(args.path, args.repo_root)
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
