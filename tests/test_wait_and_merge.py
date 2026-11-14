import contextlib
import datetime
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import wait_and_merge as wm  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.utc = datetime.datetime(2026, 11, 14, 7, 0, 0, tzinfo=datetime.timezone.utc)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.utc += datetime.timedelta(seconds=seconds)

    def now_utc(self) -> datetime.datetime:
        return self.utc


def make_pr(
    *,
    state: str = "OPEN",
    mergeable: str = "MERGEABLE",
    merge_state: str = "CLEAN",
    review_decision: str = "",
    rollup: list | None = None,
    merge_oid: str | None = None,
) -> dict:
    return {
        "number": 15,
        "state": state,
        "url": "https://github.com/oil-oil/oil-ui-gallery/pull/15",
        "isDraft": False,
        "headRefName": "fix/store-checkout-isolation",
        "headRefOid": "c8cd904",
        "headRepositoryOwner": {"login": "oil-oil"},
        "baseRefName": "main",
        "mergeable": mergeable,
        "mergeStateStatus": merge_state,
        "reviewDecision": review_decision,
        "statusCheckRollup": rollup if rollup is not None else [],
        "mergedAt": "2026-11-14T07:05:00Z" if state == "MERGED" else None,
        "mergeCommit": {"oid": merge_oid or "1b7e9ff"} if state == "MERGED" else None,
    }


class WaitAndMergeTests(unittest.TestCase):
    def run_flow(self, runner, clock: FakeClock, **kwargs) -> tuple[int, dict]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = wm.wait_and_merge(
                pr="15",
                repo="oil-oil/oil-ui-gallery",
                run=runner,
                sleep_fn=clock.sleep,
                clock_fn=clock.monotonic,
                now_utc_fn=clock.now_utc,
                **kwargs,
            )
        return code, json.loads(buf.getvalue())

    def test_clean_pr_merges_and_deletes_remote_branch(self) -> None:
        clock = FakeClock()
        calls: list[list[str]] = []
        merged = False

        def runner(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
            nonlocal merged
            calls.append(cmd)
            if cmd[:3] == ["gh", "pr", "view"]:
                data = make_pr(state="MERGED", merge_oid="1b7e9ff") if merged else make_pr()
                return subprocess.CompletedProcess(cmd, 0, json.dumps(data), "")
            if cmd[:3] == ["gh", "pr", "merge"]:
                merged = True
                return subprocess.CompletedProcess(cmd, 0, "Merged", "")
            if cmd[:3] == ["gh", "api", "-X"] and "DELETE" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            raise AssertionError(f"unexpected command: {cmd}")

        code, out = self.run_flow(runner, clock)
        self.assertEqual(code, wm.EXIT_MERGED)
        self.assertEqual(out["status"], "MERGED")
        self.assertEqual(out["mergeCommit"], "1b7e9ff")
        self.assertTrue(out["remoteBranchDeleted"])
        self.assertTrue(
            any("repos/oil-oil/oil-ui-gallery/git/refs/heads/fix/store-checkout-isolation" in " ".join(c) for c in calls)
        )

    def test_stale_vercel_webhook_bypasses_infinite_pending_when_vercel_ready(self) -> None:
        clock = FakeClock()
        merged = False
        vercel_Rollup = [
            {
                "__typename": "StatusContext",
                "context": "Vercel",
                "state": "PENDING",
                "startedAt": "2026-11-13T15:04:03Z",
                "targetUrl": "https://vercel.com/oiloils-projects/oil-ui-gallery/yGUT2c871dAJdkB2pDEp1fJ22Mnd",
            },
            {
                "__typename": "CheckRun",
                "name": "Vercel Preview Comments",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "detailsUrl": "https://vercel.com/github",
            },
        ]
        inspected: list[str] = []

        def runner(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
            nonlocal merged
            if cmd[:3] == ["gh", "pr", "view"]:
                data = (
                    make_pr(state="MERGED", merge_oid="1b7e9ff")
                    if merged
                    else make_pr(merge_state="UNSTABLE", rollup=vercel_Rollup)
                )
                return subprocess.CompletedProcess(cmd, 0, json.dumps(data), "")
            if cmd[:2] == ["/usr/local/bin/vercel", "inspect"]:
                inspected.append(cmd[2])
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "  General\n    id\tdpl_yGUT2c871dAJdkB2pDEp1fJ22Mnd\n    status\t● Ready\n",
                    "",
                )
            if cmd[:3] == ["gh", "pr", "merge"]:
                merged = True
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[:3] == ["gh", "api", "-X"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            raise AssertionError(f"unexpected command: {cmd}")

        code, out = self.run_flow(runner, clock, vercel_bin="/usr/local/bin/vercel")
        self.assertEqual(code, wm.EXIT_MERGED)
        self.assertEqual(out["status"], "MERGED")
        self.assertEqual(out["bypassReason"], "vercel_ready_webhook_stale")
        self.assertEqual(inspected, ["dpl_yGUT2c871dAJdkB2pDEp1fJ22Mnd"])
        self.assertEqual(clock.now, 0.0)

    def test_stale_vercel_webhook_fails_fast_when_vercel_errored(self) -> None:
        clock = FakeClock()
        rollup = [
            {
                "__typename": "StatusContext",
                "context": "Vercel",
                "state": "PENDING",
                "startedAt": "2026-11-13T15:04:03Z",
                "targetUrl": "https://vercel.com/oiloils-projects/oil-ui-gallery/yGUT2c871dAJdkB2pDEp1fJ22Mnd",
            }
        ]

        def runner(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["gh", "pr", "view"]:
                return subprocess.CompletedProcess(cmd, 0, json.dumps(make_pr(merge_state="UNSTABLE", rollup=rollup)), "")
            if cmd[:2] == ["/usr/local/bin/vercel", "inspect"]:
                return subprocess.CompletedProcess(cmd, 0, "    status\t● Error\n", "")
            raise AssertionError(f"unexpected command: {cmd}")

        code, out = self.run_flow(runner, clock, vercel_bin="/usr/local/bin/vercel")
        self.assertEqual(code, wm.EXIT_CHECKS_FAILED)
        self.assertEqual(out["status"], "CHECKS_FAILED")
        self.assertEqual(out["failedChecks"][0]["vercelStatus"], "Error")

    def test_failed_check_run_exits_immediately(self) -> None:
        clock = FakeClock()
        rollup = [
            {"__typename": "CheckRun", "name": "unit-tests", "status": "COMPLETED", "conclusion": "FAILURE"},
            {"__typename": "CheckRun", "name": "lint", "status": "IN_PROGRESS", "conclusion": ""},
        ]

        def runner(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(make_pr(rollup=rollup)), "")

        code, out = self.run_flow(runner, clock)
        self.assertEqual(code, wm.EXIT_CHECKS_FAILED)
        self.assertEqual(out["failedChecks"][0]["name"], "unit-tests")
        self.assertEqual(clock.now, 0.0)

    def test_conflict_exits_immediately(self) -> None:
        clock = FakeClock()

        def runner(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps(make_pr(mergeable="CONFLICTING", merge_state="DIRTY")), ""
            )

        code, out = self.run_flow(runner, clock)
        self.assertEqual(code, wm.EXIT_CONFLICT)
        self.assertEqual(out["status"], "CONFLICT")

    def test_pending_check_respects_hard_timeout(self) -> None:
        clock = FakeClock()
        rollup = [{"__typename": "CheckRun", "name": "ci", "status": "IN_PROGRESS", "conclusion": ""}]

        def runner(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(make_pr(rollup=rollup)), "")

        code, out = self.run_flow(runner, clock, timeout=25, interval=10)
        self.assertEqual(code, wm.EXIT_CHECKS_TIMEOUT)
        self.assertEqual(out["status"], "CHECKS_TIMEOUT")
        self.assertGreaterEqual(clock.now, 25.0)
        self.assertLessEqual(clock.now, 30.0)

    def test_refuses_false_positive_when_merge_command_leaves_pr_open(self) -> None:
        clock = FakeClock()

        def runner(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["gh", "pr", "view"]:
                return subprocess.CompletedProcess(cmd, 0, json.dumps(make_pr(state="OPEN")), "")
            if cmd[:3] == ["gh", "pr", "merge"]:
                return subprocess.CompletedProcess(cmd, 0, "Auto-merge enabled", "")
            raise AssertionError(f"unexpected command: {cmd}")

        code, out = self.run_flow(runner, clock)
        self.assertEqual(code, wm.EXIT_MERGE_NOT_COMPLETED)
        self.assertEqual(out["status"], "MERGE_NOT_COMPLETED")


if __name__ == "__main__":
    unittest.main()
