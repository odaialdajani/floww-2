#!/usr/bin/env python3
"""Self-check the durable PR 1..131 audit package.

This is an engineering evidence gate. It never grants owner acceptance,
commissioning approval, trading permission, or historical-data recovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ancestor(older: str, newer: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", action="store_true", help="also require origin/main to be current HEAD")
    args = parser.parse_args()

    manifest = json.loads((HERE / "manifest.json").read_text())
    expected = set(manifest["artifacts"])
    actual = {p.name for p in HERE.iterdir() if p.is_file()}
    assert actual == expected | {"manifest.json"}, sorted(actual ^ (expected | {"manifest.json"}))
    for name, digest in manifest["artifacts"].items():
        assert sha(HERE / name) == digest, f"artifact changed: {name}"

    inventory = json.loads((HERE / "inventory.json").read_text())
    rows = inventory["rows"]
    numbers = [row["number"] for row in rows]
    assert len(rows) == 131
    assert sorted(numbers) == list(range(1, 132))
    assert len(set(numbers)) == 131
    assert all(row["pr_url"].endswith(f"/pull/{row['number']}") for row in rows)
    assert all(row["evidence_keys"] for row in rows)
    assert [lane["range"] for lane in inventory["lanes"]] == [[1, 43], [44, 87], [88, 131]]

    merge = json.loads((HERE / "merge-131.json").read_text())
    assert merge["pr"]["state"] == "MERGED"
    assert merge["pr"]["headRefOid"] == "97433e4bf36cb7e0b81623351116198aef535f64"
    merge_sha = merge["verified_origin_main"]
    assert merge_sha == merge["pr"]["mergeCommit"]["oid"]
    assert ancestor(merge["pr"]["headRefOid"], merge_sha)

    findings = json.loads((HERE / "findings.json").read_text())
    expected_findings = {
        "SCOUT-BOUNDARY",
        "ABLATION-LOCAL",
        "FLOW-FUSION-LOSS",
        "VOLUME-UNKNOWN-TO-ZERO",
        "BRIEF-CROSS-TICKER-EXPORT",
    }
    assert {finding["id"] for finding in findings["findings"]} == expected_findings
    current_head = git("rev-parse", "HEAD")
    assert ancestor(inventory["current_local_head"], current_head)
    for finding in findings["findings"]:
        assert (ROOT / finding["test_file"]).is_file(), finding["test_file"]
        assert ancestor(finding["fix_commit"], current_head), finding["fix_commit"]

    checks = json.loads((HERE / "checks.json").read_text())
    for name in ["targeted_regression", "backend_full", "frontend_full", "pr_131_merge"]:
        assert checks[name]["exit_code"] == 0, name
    assert "passed" in checks["backend_full"]["result"]
    assert checks["frontend_full"]["result"]

    baseline = json.loads((HERE / "baseline.json").read_text())
    for path, expected_hash in baseline["dirty_hashes"].items():
        assert sha(ROOT / path) == expected_hash, f"concurrent dirty file changed: {path}"

    if args.remote:
        assert git("rev-parse", "origin/main") == current_head

    print(json.dumps({
        "passed": True,
        "rows": 131,
        "findings_fixed": len(findings["findings"]),
        "merge_commit": merge_sha,
        "current_head": current_head,
        "remote_checked": args.remote,
    }, indent=2))


if __name__ == "__main__":
    main()
