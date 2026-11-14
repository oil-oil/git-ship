#!/usr/bin/env python3
"""Bounded PR check waiter, stale Vercel status verifier, and verified merger for git-ship."""

from __future__ import annotations

import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from typing import Any, Callable

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
VERCEL_TARGET_RE = re.compile(
    r"^https?://vercel\.com/[^/]+/[^/]+/([A-Za-z0-9_]+)(?:[/?#]|$)",
    re.IGNORECASE,
)

EXIT_MERGED = 0
EXIT_CLOSED = 2
EXIT_EXTERNAL_BLOCKER = 3
EXIT_CONFLICT = 4
EXIT_BEHIND = 5
EXIT_CHECKS_FAILED = 6
EXIT_CHECKS_TIMEOUT = 7
EXIT_MERGE_NOT_COMPLETED = 8

PASS_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
FAIL_CONCLUSIONS = {
    "FAILURE",
    "TIMED_OUT",
    "CANCELLED",
    "ACTION_REQUIRED",
    "STARTUP_FAILURE",
    "STALE",
}

Runner = Callable[[list[str], int], subprocess.CompletedProcess[str]]


def default_runner(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def parse_iso_age_seconds(value: str | None, now_utc: datetime.datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        parsed = datetime.datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    reference = now_utc or datetime.datetime.now(datetime.timezone.utc)
    return max(0.0, (reference - parsed).total_seconds())


def resolve_repo(repo: str | None, run: Runner) -> str:
    if repo:
        return repo
    proc = run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], 15)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"failed to determine repository: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def fetch_pr(pr: str, repo: str, run: Runner) -> dict[str, Any]:
    fields = ",".join(
        [
            "number",
            "state",
            "url",
            "isDraft",
            "headRefName",
            "headRefOid",
            "headRepositoryOwner",
            "baseRefName",
            "mergeable",
            "mergeStateStatus",
            "reviewDecision",
            "statusCheckRollup",
            "mergedAt",
            "mergeCommit",
        ]
    )
    proc = run(["gh", "pr", "view", str(pr), "--repo", repo, "--json", fields], 20)
    if proc.returncode != 0:
        raise RuntimeError(f"gh pr view failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return json.loads(proc.stdout)


def classify_checks(rollup: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    passed: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for item in rollup or []:
        kind = item.get("__typename")
        if kind == "StatusContext" or ("context" in item and "name" not in item):
            name = item.get("context") or "status"
            state = (item.get("state") or "").upper()
            entry = {
                "kind": "StatusContext",
                "name": name,
                "state": state,
                "url": item.get("targetUrl") or "",
                "startedAt": item.get("startedAt") or item.get("createdAt"),
            }
            if state == "SUCCESS":
                passed.append(entry)
            elif state in {"PENDING", "EXPECTED"}:
                pending.append(entry)
            else:
                failed.append(entry)
        else:
            name = item.get("name") or "check"
            status = (item.get("status") or "").upper()
            conclusion = (item.get("conclusion") or "").upper()
            entry = {
                "kind": "CheckRun",
                "name": name,
                "status": status,
                "conclusion": conclusion,
                "url": item.get("detailsUrl") or item.get("url") or "",
                "startedAt": item.get("startedAt"),
            }
            if status != "COMPLETED":
                pending.append(entry)
            elif conclusion in PASS_CONCLUSIONS:
                passed.append(entry)
            elif conclusion in FAIL_CONCLUSIONS or conclusion:
                failed.append(entry)
            else:
                pending.append(entry)

    return passed, pending, failed


def is_vercel_status(entry: dict[str, Any]) -> bool:
    if entry.get("kind") != "StatusContext":
        return False
    name = (entry.get("name") or "").lower()
    url = (entry.get("url") or "").lower()
    return "vercel" in name or "vercel.com/" in url or ".vercel.app" in url


def extract_vercel_deployment_ref(url: str) -> str | None:
    if not url:
        return None
    match = VERCEL_TARGET_RE.match(url.strip())
    if match:
        raw_id = match.group(1)
        return raw_id if raw_id.startswith("dpl_") else f"dpl_{raw_id}"
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.hostname and parsed.hostname.endswith(".vercel.app"):
        return f"{parsed.scheme}://{parsed.hostname}"
    return None


def probe_vercel_status(
    url: str,
    run: Runner,
    vercel_bin: str | None = None,
) -> str | None:
    binary = vercel_bin if vercel_bin is not None else shutil.which("vercel")
    if not binary:
        return None
    ref = extract_vercel_deployment_ref(url)
    if not ref:
        return None
    try:
        proc = run([binary, "inspect", ref], 15)
    except subprocess.TimeoutExpired:
        return None
    output = strip_ansi(f"{proc.stdout}\n{proc.stderr}")
    match = re.search(
        r"^\s*status\s+(?:●\s*)?(Ready|Error|Canceled|Building|Queued|Initializing)\b",
        output,
        re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return None
    return match.group(1).capitalize()


def delete_remote_branch_if_same_repo(pr_data: dict[str, Any], repo: str, run: Runner) -> bool:
    head_ref = pr_data.get("headRefName") or ""
    base_ref = pr_data.get("baseRefName") or ""
    if not head_ref or head_ref == base_ref:
        return False
    owner = repo.split("/", 1)[0]
    head_owner = (pr_data.get("headRepositoryOwner") or {}).get("login")
    if head_owner and head_owner.lower() != owner.lower():
        return False
    encoded_ref = urllib.parse.quote(head_ref, safe="/")
    proc = run(["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{encoded_ref}"], 15)
    return proc.returncode == 0


def emit(payload: dict[str, Any], code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def wait_and_merge(
    pr: str,
    repo: str | None = None,
    strategy: str = "squash",
    timeout: int = 240,
    interval: int = 8,
    stale_grace: int = 30,
    dry_run: bool = False,
    run: Runner = default_runner,
    sleep_fn: Callable[[float], None] = time.sleep,
    clock_fn: Callable[[], float] = time.monotonic,
    now_utc_fn: Callable[[], datetime.datetime] | None = None,
    vercel_bin: str | None = None,
) -> int:
    target_repo = resolve_repo(repo, run)
    start = clock_fn()
    marked_ready = False
    bypass_reason: str | None = None
    snapshot: dict[str, Any] = {}

    while True:
        snapshot = fetch_pr(pr, target_repo, run)
        state = (snapshot.get("state") or "").upper()
        pr_url = snapshot.get("url") or ""

        if state == "MERGED":
            delete_remote_branch_if_same_repo(snapshot, target_repo, run)
            return emit(
                {
                    "status": "MERGED",
                    "repository": target_repo,
                    "number": snapshot.get("number"),
                    "url": pr_url,
                    "mergeCommit": (snapshot.get("mergeCommit") or {}).get("oid"),
                    "mergedAt": snapshot.get("mergedAt"),
                },
                EXIT_MERGED,
            )

        if state == "CLOSED":
            return emit(
                {
                    "status": "CLOSED",
                    "repository": target_repo,
                    "number": snapshot.get("number"),
                    "url": pr_url,
                },
                EXIT_CLOSED,
            )

        if snapshot.get("isDraft") and not marked_ready:
            ready_proc = run(["gh", "pr", "ready", str(pr), "--repo", target_repo], 15)
            if ready_proc.returncode != 0:
                return emit(
                    {
                        "status": "EXTERNAL_BLOCKER",
                        "reason": "draft_cannot_be_marked_ready",
                        "detail": ready_proc.stderr.strip() or ready_proc.stdout.strip(),
                        "url": pr_url,
                    },
                    EXIT_EXTERNAL_BLOCKER,
                )
            marked_ready = True
            snapshot = fetch_pr(pr, target_repo, run)

        mergeable = (snapshot.get("mergeable") or "").upper()
        merge_state = (snapshot.get("mergeStateStatus") or "").upper()
        review_decision = (snapshot.get("reviewDecision") or "").upper()

        if mergeable == "CONFLICTING" or merge_state == "DIRTY":
            return emit(
                {
                    "status": "CONFLICT",
                    "repository": target_repo,
                    "number": snapshot.get("number"),
                    "baseRefName": snapshot.get("baseRefName"),
                    "headRefName": snapshot.get("headRefName"),
                    "url": pr_url,
                },
                EXIT_CONFLICT,
            )

        if merge_state == "BEHIND":
            return emit(
                {
                    "status": "BEHIND",
                    "repository": target_repo,
                    "number": snapshot.get("number"),
                    "baseRefName": snapshot.get("baseRefName"),
                    "headRefName": snapshot.get("headRefName"),
                    "url": pr_url,
                },
                EXIT_BEHIND,
            )

        if review_decision == "CHANGES_REQUESTED" or (
            merge_state == "BLOCKED" and review_decision == "REVIEW_REQUIRED"
        ):
            return emit(
                {
                    "status": "EXTERNAL_BLOCKER",
                    "reason": review_decision.lower(),
                    "repository": target_repo,
                    "number": snapshot.get("number"),
                    "url": pr_url,
                },
                EXIT_EXTERNAL_BLOCKER,
            )

        passed, pending, failed = classify_checks(snapshot.get("statusCheckRollup"))

        if failed:
            return emit(
                {
                    "status": "CHECKS_FAILED",
                    "repository": target_repo,
                    "number": snapshot.get("number"),
                    "url": pr_url,
                    "failedChecks": failed,
                },
                EXIT_CHECKS_FAILED,
            )

        elapsed = clock_fn() - start

        if not pending:
            if mergeable == "UNKNOWN" and elapsed < timeout:
                sleep_fn(min(3.0, max(0.5, timeout - elapsed)))
                continue
            if merge_state == "BLOCKED":
                return emit(
                    {
                        "status": "EXTERNAL_BLOCKER",
                        "reason": "branch_protection_blocked",
                        "mergeStateStatus": merge_state,
                        "reviewDecision": review_decision,
                        "url": pr_url,
                    },
                    EXIT_EXTERNAL_BLOCKER,
                )
            break

        now_utc = now_utc_fn() if now_utc_fn else datetime.datetime.now(datetime.timezone.utc)
        if (
            mergeable == "MERGEABLE"
            and merge_state != "BLOCKED"
            and all(is_vercel_status(item) for item in pending)
        ):
            oldest_age = max(
                (parse_iso_age_seconds(item.get("startedAt"), now_utc) or 0.0 for item in pending),
                default=0.0,
            )
            if elapsed >= stale_grace or oldest_age >= 60.0:
                vercel_states = [
                    probe_vercel_status(item.get("url") or "", run, vercel_bin=vercel_bin)
                    for item in pending
                ]
                failed_vercel = [
                    {**item, "vercelStatus": v_state}
                    for item, v_state in zip(pending, vercel_states)
                    if v_state in {"Error", "Canceled"}
                ]
                if failed_vercel:
                    return emit(
                        {
                            "status": "CHECKS_FAILED",
                            "repository": target_repo,
                            "number": snapshot.get("number"),
                            "url": pr_url,
                            "failedChecks": failed_vercel,
                        },
                        EXIT_CHECKS_FAILED,
                    )
                if vercel_states and all(v_state == "Ready" for v_state in vercel_states):
                    bypass_reason = "vercel_ready_webhook_stale"
                    break

        if elapsed >= timeout:
            return emit(
                {
                    "status": "CHECKS_TIMEOUT",
                    "repository": target_repo,
                    "number": snapshot.get("number"),
                    "url": pr_url,
                    "elapsedSeconds": round(elapsed, 1),
                    "mergeable": mergeable,
                    "mergeStateStatus": merge_state,
                    "pendingChecks": pending,
                    "passedCount": len(passed),
                },
                EXIT_CHECKS_TIMEOUT,
            )

        sleep_fn(min(float(interval), max(0.5, timeout - elapsed)))

    if dry_run:
        return emit(
            {
                "status": "READY_TO_MERGE",
                "repository": target_repo,
                "number": snapshot.get("number"),
                "url": snapshot.get("url"),
                "bypassReason": bypass_reason,
            },
            EXIT_MERGED,
        )

    merge_proc = run(["gh", "pr", "merge", str(pr), "--repo", target_repo, f"--{strategy}"], 30)
    if merge_proc.returncode != 0:
        detail = (merge_proc.stderr or merge_proc.stdout).strip()
        lowered = detail.lower()
        if "conflict" in lowered or "not mergeable" in lowered or "out-of-date" in lowered or "behind" in lowered:
            return emit(
                {
                    "status": "CONFLICT",
                    "repository": target_repo,
                    "number": snapshot.get("number"),
                    "detail": detail,
                    "url": snapshot.get("url"),
                },
                EXIT_CONFLICT,
            )
        if "protected branch" in lowered or "review" in lowered or "permission" in lowered or "authorized" in lowered:
            return emit(
                {
                    "status": "EXTERNAL_BLOCKER",
                    "reason": "merge_rejected",
                    "detail": detail,
                    "url": snapshot.get("url"),
                },
                EXIT_EXTERNAL_BLOCKER,
            )
        return emit(
            {
                "status": "MERGE_NOT_COMPLETED",
                "repository": target_repo,
                "number": snapshot.get("number"),
                "detail": detail,
                "url": snapshot.get("url"),
            },
            EXIT_MERGE_NOT_COMPLETED,
        )

    verify_deadline = clock_fn() + 30.0
    verified = snapshot
    while True:
        verified = fetch_pr(pr, target_repo, run)
        if (verified.get("state") or "").upper() == "MERGED":
            break
        if clock_fn() >= verify_deadline:
            return emit(
                {
                    "status": "MERGE_NOT_COMPLETED",
                    "repository": target_repo,
                    "number": verified.get("number"),
                    "state": verified.get("state"),
                    "url": verified.get("url"),
                    "detail": "gh pr merge returned 0 but PR state is not MERGED",
                },
                EXIT_MERGE_NOT_COMPLETED,
            )
        sleep_fn(2.0)

    branch_deleted = delete_remote_branch_if_same_repo(verified, target_repo, run)
    return emit(
        {
            "status": "MERGED",
            "repository": target_repo,
            "number": verified.get("number"),
            "url": verified.get("url"),
            "headRefName": verified.get("headRefName"),
            "baseRefName": verified.get("baseRefName"),
            "mergeCommit": (verified.get("mergeCommit") or {}).get("oid"),
            "mergedAt": verified.get("mergedAt"),
            "remoteBranchDeleted": branch_deleted,
            "bypassReason": bypass_reason,
        },
        EXIT_MERGED,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Wait for PR checks with a hard timeout, verify stale Vercel webhooks, squash-merge, and confirm MERGED state."
    )
    parser.add_argument("pr", help="PR number, branch name, or URL")
    parser.add_argument("--repo", help="GitHub repository in owner/repo format")
    parser.add_argument(
        "--strategy",
        choices=("squash", "merge", "rebase"),
        default="squash",
        help="Merge strategy (default: squash)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=240,
        help="Maximum seconds to wait for pending checks before exiting (default: 240)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=8,
        help="Polling interval in seconds (default: 8)",
    )
    parser.add_argument(
        "--stale-grace",
        type=int,
        default=30,
        help="Seconds before probing Vercel CLI for a pending Vercel Commit Status (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify readiness without executing gh pr merge",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return wait_and_merge(
            pr=args.pr,
            repo=args.repo,
            strategy=args.strategy,
            timeout=args.timeout,
            interval=args.interval,
            stale_grace=args.stale_grace,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "ERROR", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
