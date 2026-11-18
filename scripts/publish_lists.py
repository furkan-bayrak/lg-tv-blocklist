#!/usr/bin/env python3
"""Publish generated lists only while the validated inputs still match origin."""

import argparse
import hashlib
import os
import re
import subprocess
import sys

import build

INPUT_PATHS = ("src/", "scripts/", ".github/workflows/", ".gitattributes")
DEFERRED = "DEFERRED: generation or validation inputs advanced; newer revision must publish"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # Keep push rejection reasons stable for the single reconciliation decision.
    return subprocess.run(
        ["git", *args], cwd=build.ROOT, env={**os.environ, "LC_ALL": "C"},
        capture_output=True, text=True, errors="replace", check=check,
    )


def fetch_tip(ref: str) -> str:
    git("fetch", "--no-tags", "origin", ref)
    return git("rev-parse", "--verify", "FETCH_HEAD^{commit}").stdout.strip()


def is_ancestor(ancestor: str, tip: str) -> bool:
    result = git("merge-base", "--is-ancestor", ancestor, tip, check=False)
    if result.returncode == 1:
        return False
    result.check_returncode()
    return True


def inputs_match(validated_head: str, tip: str) -> bool:
    if not is_ancestor(validated_head, tip):
        raise RuntimeError("validated head is no longer an ancestor of the destination branch")
    result = git("diff", "--quiet", "--no-ext-diff", validated_head, tip, "--", *INPUT_PATHS,
                 check=False)
    if result.returncode == 1:
        return False
    result.check_returncode()
    return True


def without_timestamp(content: bytes) -> bytes:
    return b"".join(line for line in content.splitlines(keepends=True)
                    if not line.startswith(b"# Updated:"))


def artifacts_match(outputs: dict[str, str]) -> bool:
    checksums = []
    matches = True
    try:
        for name, expected in sorted(outputs.items()):
            content = (build.LISTS / name).read_bytes()
            matches &= without_timestamp(content) == without_timestamp(expected.encode("utf-8"))
            checksums.append(f"{hashlib.sha256(content).hexdigest()}  {name}\n")
        manifest = (build.LISTS / "SHA256SUMS").read_bytes()
    except FileNotFoundError:
        return False
    return matches and manifest == "".join(checksums).encode("ascii")


def prepare_commit(tip: str, current_head: str) -> str | None:
    if tip != current_head:
        git("switch", "--detach", tip)
    outputs = build.dry_run()
    if artifacts_match(outputs):
        return None

    build.build()
    subprocess.run(["sha256sum", "--strict", "-c", "SHA256SUMS"], cwd=build.LISTS, check=True)
    git("add", "--", "lists/SHA256SUMS", *(f"lists/{name}" for name in sorted(outputs)))
    git("-c", "user.name=github-actions[bot]",
        "-c", "user.email=github-actions[bot]@users.noreply.github.com",
        "commit", "-m", "chore: regenerate blocklists [skip ci]")
    return git("rev-parse", "HEAD").stdout.strip()


def push_rejected_for_movement(result: subprocess.CompletedProcess[str], ref: str, tip: str) -> bool:
    for line in result.stdout.splitlines():
        if not line.startswith("!\t"):
            continue
        reason = line.rsplit("\t", 1)[-1]
        if reason in {"[rejected] (fetch first)", "[rejected] (non-fast-forward)"}:
            return True
        if reason == "[remote rejected] (failed to update ref)":
            # The server may have raced after advertising the old ref.
            lock_error = rf"cannot lock ref '{re.escape(ref)}': is at [0-9a-f]{{40}} but expected {tip}\b"
            return re.search(lock_error, result.stderr) is not None
    return False


def publish(validated_head: str, branch: str) -> int:
    ref = f"refs/heads/{branch}"
    if not re.fullmatch(r"[0-9a-fA-F]{40}", validated_head):
        print("ERROR: --validated-head must be a full commit SHA")
        return 2
    validated_head = validated_head.lower()
    try:
        if git("check-ref-format", ref, check=False).returncode != 0:
            print("ERROR: --branch must name a valid branch")
            return 2
        current_head = git("rev-parse", "HEAD").stdout.strip()
        if current_head != validated_head or git("status", "--porcelain", "--untracked-files=all").stdout:
            print("ERROR: checkout must be clean and at the validated head")
            return 2
        fetch_urls = git("remote", "get-url", "--all", "origin").stdout.splitlines()
        push_urls = git("remote", "get-url", "--push", "--all", "origin").stdout.splitlines()
        if len(fetch_urls) != 1 or fetch_urls != push_urls:
            print("ERROR: origin must use one matching fetch and push destination")
            return 2

        tip = fetch_tip(ref)
        for attempt in range(2):
            if not inputs_match(validated_head, tip):
                print(DEFERRED)
                return 0
            candidate = prepare_commit(tip, current_head)
            if candidate is None:
                print("UNCHANGED: generated bodies and checksums match")
                return 0

            result = git("push", "--porcelain", "--no-follow-tags", "origin", f"HEAD:{ref}", check=False)
            if result.returncode == 0:
                print(f"PUBLISHED: {candidate}")
                return 0

            # A failed client can still have updated the ref. Observe origin
            # before deciding whether another write is safe.
            observed_tip = fetch_tip(ref)
            if is_ancestor(candidate, observed_tip):
                print(f"PUBLISHED: {candidate} confirmed on origin")
                return 0
            if (attempt == 0 and observed_tip != tip and is_ancestor(tip, observed_tip)
                    and push_rejected_for_movement(result, ref, tip)):
                tip, current_head = observed_tip, candidate
                continue
            result.check_returncode()
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        print(f"ERROR: {exc}" + (f"\n{detail}" if detail else ""))
        return 1
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validated-head", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args(argv)
    return publish(args.validated_head, args.branch)


if __name__ == "__main__":
    sys.exit(main())
