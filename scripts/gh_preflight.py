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

`gh` being logged in is not enough: the run pushes its fix branches with
plain git, which keeps its own GitHub sign-in. So git's access is checked
separately, and a git that can't reach or sign in to GitHub is reported as
exactly that -- never as "your branch isn't pushed". When git can't get
through, the branch is looked up through `gh` instead, so the message still
says truthfully whether it is on GitHub.

Exits 0 when ok, 1 otherwise. Every reason is listed in "problems", in
plain words, each ending with what to do about it.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from urllib.parse import quote

WRITE_PERMISSIONS = {"ADMIN", "MAINTAIN", "WRITE"}

# Network git calls can stall on a sign-in prompt nobody can answer; give up
# rather than hang the pipeline.
GIT_NETWORK_TIMEOUT = 90

# A ref name only ever used in a `git push --dry-run`, so nothing is created.
PUSH_PROBE_REF = "refs/heads/agentic-qe-preflight-push-check"

# How git words its failures. Sign-in is checked first: "unable to access"
# also prefixes HTTP 403s.
SIGN_IN_SIGNS = (
    "authentication failed",
    "could not read username",
    "could not read password",
    "terminal prompts disabled",
    "invalid username or password",
    "invalid credentials",
    "logon failed",
    "permission denied",
    "permission to",
    "error: 403",
    "returned error: 401",
    "repository not found",
    "host key verification failed",
)
NETWORK_SIGNS = (
    "could not resolve host",
    "could not resolve proxy",
    "failed to connect",
    "couldn't connect",
    "connection timed out",
    "operation timed out",
    "connection refused",
    "connection reset",
    "network is unreachable",
    "ssl",
    "unable to access",
)


def run(cmd, cwd, timeout=None, env=None):
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return None, "", f"gave up after {timeout} seconds with no answer"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def run_git_network(cmd, cwd):
    """Run a git command that talks to the remote, failing fast instead of
    waiting for a password prompt (no one can type into it here)."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return run(cmd, cwd, timeout=GIT_NETWORK_TIMEOUT, env=env)


def git_said(err):
    """The most telling line of git's error output, for the message."""
    lines = [line.strip() for line in err.splitlines() if line.strip()]
    for line in lines:
        if line.lower().startswith(("fatal:", "error:", "remote:")):
            return line
    return lines[-1] if lines else "no error message"


def git_access_problem(err, remote, remote_url, repo, timed_out):
    """Turn a failed git network call into one plain-language problem."""
    said = git_said(err)
    lowered = err.lower()
    ssh = remote_url.startswith(("git@", "ssh://"))

    if timed_out:
        return (
            f"git got no answer from GitHub within {GIT_NETWORK_TIMEOUT} seconds. It may be "
            "waiting for a GitHub sign-in window, or the network may be blocking it. "
            "Fix: run `gh auth setup-git` once so git uses your gh sign-in, then run the "
            f"pipeline again. If it still hangs, run `git fetch {remote}` in a terminal to see why."
        )
    if any(sign in lowered for sign in SIGN_IN_SIGNS):
        if ssh:
            return (
                f"git can't sign in to GitHub with your SSH key (remote '{remote}' uses SSH). "
                "Fix: either run `ssh -T git@github.com` to see what's wrong with the key, or "
                f"switch the remote to HTTPS and let git use your gh sign-in: "
                f"`git remote set-url {remote} https://github.com/{repo}.git` and then "
                f"`gh auth setup-git`. Then run the pipeline again. (git said: {said})"
            )
        return (
            "git on this computer can't sign in to GitHub, so the run wouldn't be able to push "
            "its fix branches. Your gh login works, but git keeps its own GitHub sign-in. "
            "Fix: run `gh auth setup-git` once (it makes git use your gh sign-in), then run the "
            f"pipeline again. (git said: {said})"
        )
    if any(sign in lowered for sign in NETWORK_SIGNS):
        return (
            "git couldn't connect to GitHub from here, though gh could. Check your internet "
            "connection, VPN or proxy; if Claude Code's sandbox is on, allow github.com. "
            f"Then run the pipeline again. (git said: {said})"
        )
    return (
        f"git couldn't talk to GitHub ({remote_url}). Run `git fetch {remote}` in a terminal "
        f"to see the full error. (git said: {said})"
    )


def branch_on_github(repo, branch, repo_root):
    """Ask GitHub through gh whether the branch exists, for when git itself
    can't get through. True, False, or None if gh can't tell either."""
    code, _, err = run(
        ["gh", "api", f"repos/{repo}/branches/{quote(branch, safe='')}", "--jq", ".name"],
        repo_root,
        timeout=GIT_NETWORK_TIMEOUT,
    )
    if code == 0:
        return True
    if "404" in err:
        return False
    return None


def not_pushed_problem(branch, remote):
    return (
        f"your branch '{branch}' isn't on GitHub yet. Fix runs open pull requests into this "
        f"branch, so GitHub needs a copy first. Fix: run `git push -u {remote} {branch}`, then "
        "run the pipeline again -- or run without --live for a report-only run."
    )


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

    branch_problems = check_branch(repo_root, remote, remote_url, result["repo"], branch)
    problems.extend(branch_problems)
    if not branch_problems:
        result["pr_base_branch"] = branch

    result["ok"] = not problems
    return result


def check_branch(repo_root, remote, remote_url, repo, branch):
    """Can git reach and push to GitHub, is the branch there, and is HEAD
    already pushed? An auto-fix branch is cut from HEAD, so anything not yet
    pushed would end up in the PR."""
    # ls-remote tells "branch missing" (exit 2) apart from "couldn't reach
    # GitHub" (anything else). A failed fetch can't.
    code, out, err = run_git_network(
        ["git", "ls-remote", "--exit-code", "--heads", remote, f"refs/heads/{branch}"], repo_root
    )
    if code not in (0, 2):
        problem = git_access_problem(err, remote, remote_url, repo, timed_out=code is None)
        on_github = branch_on_github(repo, branch, repo_root)
        if on_github is True:
            return [f"your branch '{branch}' is on GitHub, so nothing needs pushing. The real problem: {problem}"]
        if on_github is False:
            return [problem, not_pushed_problem(branch, remote)]
        return [problem]

    # git can read; make sure it can also push before the run relies on it. A
    # dry run to a throwaway ref name signs in but creates nothing.
    push_code, _, push_err = run_git_network(
        ["git", "push", "--dry-run", "--quiet", remote, f"HEAD:{PUSH_PROBE_REF}"], repo_root
    )
    if push_code != 0:
        return [git_access_problem(push_err, remote, remote_url, repo, timed_out=push_code is None)]

    if code == 2:
        return [not_pushed_problem(branch, remote)]

    remote_sha = out.split()[0]
    _, head_sha, _ = run(["git", "rev-parse", "HEAD"], repo_root)
    if remote_sha == head_sha:
        return []

    # GitHub's copy differs; get its commits so the two can be compared.
    code, _, _ = run(["git", "cat-file", "-e", f"{remote_sha}^{{commit}}"], repo_root)
    if code != 0:
        code, _, err = run_git_network(
            ["git", "fetch", "--quiet", "--no-tags", remote, f"refs/heads/{branch}"], repo_root
        )
        if code != 0:
            return [git_access_problem(err, remote, remote_url, repo, timed_out=code is None)]

    code, _, _ = run(["git", "merge-base", "--is-ancestor", "HEAD", remote_sha], repo_root)
    if code == 0:
        return []  # GitHub is ahead of you; everything you have is already there

    code, _, _ = run(["git", "merge-base", "--is-ancestor", remote_sha, "HEAD"], repo_root)
    if code == 0:
        _, ahead, _ = run(["git", "rev-list", "--count", f"{remote_sha}..HEAD"], repo_root)
        count = "1 commit that isn't" if ahead == "1" else f"{ahead or 'some'} commits that aren't"
        return [
            f"your branch '{branch}' has {count} on GitHub yet. "
            "Fix runs would carry unpushed work into their pull requests. Fix: run `git push`, then run "
            "the pipeline again."
        ]
    return [
        f"your branch '{branch}' and GitHub's copy of it have each gained different commits. "
        "Fix: run `git pull` to combine them, then `git push`, then run the pipeline again."
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="the target repo's root")
    args = parser.parse_args()

    result = preflight(args.repo_root)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
