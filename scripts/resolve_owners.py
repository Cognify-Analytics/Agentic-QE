#!/usr/bin/env python3
"""Resolve file paths to owners via CODEOWNERS, and optionally to the
GitHub users who can actually be assigned.

Looks for CODEOWNERS in the conventional locations (repo root, .github/,
docs/) and matches each given path against its patterns, last match wins
(matching GitHub's own CODEOWNERS precedence rule).

Usage:
    python scripts/resolve_owners.py <path> [<path> ...] [--repo-root .]
                                     [--github-repo OWNER/REPO]

Without --github-repo nothing touches the network -- this is what a
report-only run uses. Prints JSON to stdout:

    {"files": [{"path": "src/pricing.py", "owners": ["@payments-team"],
                "source": "CODEOWNERS:src/pricing.py"}],
     "owners": ["@payments-team"]}

"owners" is the union across every path, in first-seen order. If no
CODEOWNERS file exists, or nothing matches, it is an empty list and each
file's "source" explains why -- this is not an error, it's a normal
outcome that /triage-tests must handle by filing without an assignee
rather than guessing or crashing.

With --github-repo (needs an authenticated `gh`), the owners are turned
into what GitHub will actually accept, and three more fields are added:

    "assignees":    individual logins that are assignable on the repo --
                    direct @user owners first, then members of @org/team
                    owners when the token can list them; capped at 10,
                    GitHub's limit
    "reviewers":    owners to request PR review from: assignable users plus
                    "org/team" slugs, minus the authenticated user (GitHub
                    refuses a review request from a PR's own author)
    "mention_only": owners that cannot be assigned -- emails, users without
                    repo access, teams whose members can't be listed. Name
                    them in the issue/PR body so they are still notified.
    "notes":        why anything landed in mention_only or was cut
"""

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys

CODEOWNERS_LOCATIONS = ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"]
MAX_ASSIGNEES = 10  # GitHub rejects more than this on one issue or PR


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


def _gh(args):
    proc = subprocess.run(["gh"] + args, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip()


def resolve_assignment(owners, github_repo):
    """Turn CODEOWNERS entries into assignees/reviewers GitHub will accept."""
    result = {"assignees": [], "reviewers": [], "mention_only": [], "notes": []}
    if shutil.which("gh") is None:
        result["mention_only"] = list(owners)
        result["notes"].append("gh is not installed -- nothing could be checked, so nobody is assigned")
        return result

    assignable_cache = {}

    def assignable(login):
        if login not in assignable_cache:
            code, _ = _gh(["api", "--silent", f"repos/{github_repo}/assignees/{login}"])
            assignable_cache[login] = code == 0
        return assignable_cache[login]

    # The PR author can't be requested as its own reviewer. Under an Actions
    # GITHUB_TOKEN this lookup fails, which is fine -- the bot owns nothing.
    code, me = _gh(["api", "user", "--jq", ".login"])
    me = me.lower() if code == 0 else None

    direct, from_teams = [], []
    for owner in owners:
        if not owner.startswith("@"):
            result["mention_only"].append(owner)
            result["notes"].append(f"{owner} is an email address -- GitHub can't assign by email")
            continue
        name = owner[1:]
        if "/" in name:
            org, team = name.split("/", 1)
            result["reviewers"].append(name)
            code, out = _gh(["api", "--paginate", f"orgs/{org}/teams/{team}/members", "--jq", ".[].login"])
            members = [m for m in out.splitlines() if m] if code == 0 else []
            if not members:
                result["mention_only"].append(owner)
                result["notes"].append(
                    f"{owner} is a team and its members couldn't be listed (the token may lack "
                    "read:org) -- mention it so the team is notified"
                )
            from_teams.extend(m for m in members if assignable(m))
        elif assignable(name):
            direct.append(name)
            if name.lower() != me:
                result["reviewers"].append(name)
        else:
            result["mention_only"].append(owner)
            result["notes"].append(f"{owner} can't be assigned on {github_repo} (no access to the repo)")

    seen = set()
    for login in direct + from_teams:
        if login.lower() not in seen:
            seen.add(login.lower())
            result["assignees"].append(login)
    if len(result["assignees"]) > MAX_ASSIGNEES:
        result["notes"].append(
            f"{len(result['assignees'])} assignable owners -- kept the first {MAX_ASSIGNEES} "
            "(direct owners before team members), GitHub's limit"
        )
        result["assignees"] = result["assignees"][:MAX_ASSIGNEES]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="repo-relative paths to resolve owners for")
    parser.add_argument("--repo-root", default=".", help="repo root to search for CODEOWNERS")
    parser.add_argument(
        "--github-repo",
        help="OWNER/REPO -- also check who GitHub will accept as assignee/reviewer (calls gh)",
    )
    args = parser.parse_args()

    files = [resolve_owners(path, args.repo_root) for path in args.paths]
    owners = []
    for f in files:
        owners.extend(o for o in f["owners"] if o not in owners)

    result = {"files": files, "owners": owners}
    if args.github_repo:
        if owners:
            result.update(resolve_assignment(owners, args.github_repo))
        else:
            result.update({"assignees": [], "reviewers": [], "mention_only": [], "notes": []})
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
