#!/usr/bin/env python3
"""Check that a local run can safely act on GitHub, before it tries to.

In CI the workflow hands the pipeline a GITHUB_TOKEN, GH_REPO, and a PR head
branch that is guaranteed to exist on the remote. A local `--live` run has
none of that for free, so this script works out the local equivalents up
front -- which repo, which remote, which branch a PR should target -- and
refuses (ok: false) rather than letting /triage-tests discover a problem
halfway through Stage 3.

Usage:
    python scripts/gh_preflight.py [--repo-root .]

Prints JSON to stdout:

    {"ok": true, "repo": "org/repo", "remote": "origin",
     "default_branch": "main", "start_branch": "feature/refunds",
     "pr_base_branch": "feature/refunds", "problems": []}

PR base rule (mirrors CI, where the base is always the PR's own head
branch): if you are on a branch that exists on the remote and HEAD is
already pushed, fixes target that branch. If you are on the default branch,
they target the default branch (via a PR -- never a push). A branch that is
unpushed, or has unpushed commits, is refused: an auto-fix branch cut from
it would drag those commits into the PR.

Exits 0 when ok, 1 otherwise. Every reason is listed in "problems".
"""

import argparse
import json
import shutil
import subprocess
import sys

WRITE_PERMISSIONS = {"ADMIN", "MAINTAIN", "WRITE"}


def run(cmd, cwd):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def preflight(repo_root):
    result = {
        "ok": False,
        "repo": None,
        "remote": None,
        "default_branch": None,
        "start_branch": None,
        "pr_base_branch": None,
        "problems": [],
    }
    problems = result["problems"]

    code, _, _ = run(["git", "rev-parse", "--is-inside-work-tree"], repo_root)
    if code != 0:
        problems.append("not a git repository")
        return result

    code, branch, _ = run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], repo_root)
    if code != 0 or not branch:
        problems.append("HEAD is detached -- check out a branch first")
        return result
    result["start_branch"] = branch

    # Prefer the remote this branch already tracks; fall back to origin.
    code, remote, _ = run(["git", "config", f"branch.{branch}.remote"], repo_root)
    if code != 0 or not remote or remote == ".":
        remote = "origin"
    code, remote_url, _ = run(["git", "remote", "get-url", remote], repo_root)
    if code != 0:
        problems.append(f"no git remote named '{remote}' -- add one pointing at the GitHub repo")
        return result
    result["remote"] = remote

    if shutil.which("gh") is None:
        problems.append("the GitHub CLI (gh) is not installed -- https://cli.github.com")
        return result
    code, _, err = run(["gh", "auth", "status"], repo_root)
    if code != 0:
        problems.append("gh is not authenticated -- run `gh auth login`")
        return result

    # Resolve the repo from the remote URL rather than letting gh pick among
    # several remotes -- the local equivalent of CI's GH_REPO.
    code, out, err = run(
        ["gh", "repo", "view", remote_url, "--json", "nameWithOwner,defaultBranchRef,viewerPermission"],
        repo_root,
    )
    if code != 0:
        problems.append(f"gh cannot see the repo at {remote_url}: {err or out}")
        return result
    info = json.loads(out)
    result["repo"] = info["nameWithOwner"]
    default_branch = (info.get("defaultBranchRef") or {}).get("name")
    result["default_branch"] = default_branch
    permission = info.get("viewerPermission")
    if permission not in WRITE_PERMISSIONS:
        problems.append(
            f"your GitHub permission on {info['nameWithOwner']} is {permission or 'unknown'} -- "
            "pushing auto-fix branches needs WRITE or higher"
        )

    # Is HEAD on the remote? An auto-fix branch is cut from HEAD, so anything
    # not yet pushed would end up in the PR.
    code, _, err = run(["git", "fetch", "--quiet", "--no-tags", remote, branch], repo_root)
    if code != 0:
        problems.append(
            f"branch '{branch}' is not on {remote} -- push it first (git push -u {remote} {branch}), "
            "or run without --live"
        )
    else:
        code, _, _ = run(["git", "merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD"], repo_root)
        if code != 0:
            problems.append(
                f"'{branch}' has commits not on {remote}/{branch} -- push them first, "
                "or the auto-fix PR would include them"
            )
        else:
            result["pr_base_branch"] = branch

    result["ok"] = not problems
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="the target repo's root")
    args = parser.parse_args()

    result = preflight(args.repo_root)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
