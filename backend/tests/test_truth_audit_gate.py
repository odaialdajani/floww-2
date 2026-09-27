"""Tests for the truth-audit gate (``qc/audit/truth_audit.sh``).

The gate runs as step 4 of every CI ``backend-tests`` job. Its silent-except
sibling has a self-test; this one did not, which is how it came to inspect 8 of
84 model descriptors for months while reporting PASS (see #61).

Two things are guarded here:

1. **Discovery.** Every metadata filename convention actually present in the
   repo must be matched by the ``find``. A pattern that silently stops matching
   is invisible: the gate still exits 0, just having looked at less.
2. **The WARN/FAIL split.** Rules 9-12 must keep warning rather than failing on
   commits that do not claim ML work. A gate that starts blocking every docs
   commit gets switched off, which is worse than a gate that under-reports.

Every fixture is built under ``tmp_path``; nothing here reads the live model
tree. Only changing the gate's own behaviour can break these tests.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "qc" / "audit" / "truth_audit.sh"


def _bash():
    if os.name == "nt":
        git = Path(shutil.which("git")).resolve()
        candidate = git.parent.parent / "bin" / "bash.exe"
        assert candidate.is_file(), "Git Bash is required to run the real audit gate"
        return str(candidate)
    return shutil.which("bash") or "bash"

def _run(args, **kwargs):
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    kwargs.setdefault("encoding", "utf-8")
    return subprocess.run(args, **kwargs)

def _gate(root):
    # Keep the real script unchanged while using this test's actual interpreter.
    python = shlex.quote(sys.executable.replace("\\", "/"))
    command = 'python3() { ' + python + ' "$@"; }; export -f python3; bash "$1"'
    return _run([_bash(), "-c", command, "audit-test", "qc/audit/truth_audit.sh"],
                cwd=root, capture_output=True, text=True, check=False)

def _discovered():
    # Execute the production discovery block; never duplicate its patterns here.
    source = GATE_PATH.read_text(encoding="utf-8")
    block = "MODEL_METAS=$(" + source.split("MODEL_METAS=$(", 1)[1].split("\n)", 1)[0] + "\n)"
    proc = _run([_bash(), "-c", block + '\nprintf "%s\\n" "$MODEL_METAS"'],
                cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return proc.stdout.splitlines()

# A commit subject that trips the ML/model rules, so findings are BLOCKING
# rather than WARN. A non-ML subject is used separately to pin the WARN path.
ML_SUBJECT = "chore: retrain gbm production artifacts"
DOCS_SUBJECT = "docs: refresh the status notes"

# The fixture repo is created fresh in tmp_path, so it must not depend on the
# ambient git config. A developer machine has user.name/user.email set and a CI
# runner does not. Without these, `git commit` exits 128 and every test in this
# file fails for a reason that has nothing to do with the gate -- which is
# exactly how the first CI run of this suite went red.
GIT = [
    "git",
    "-c", "user.name=truth-audit-test",
    "-c", "user.email=truth-audit-test@example.invalid",
    "-c", "commit.gpgsign=false",
    # git >= 2.35 refuses to operate in a directory owned by another user
    # ("dubious ownership", exit 128). tmp_path is not always owned by the CI
    # runner, so allow it explicitly rather than inheriting whatever
    # safe.directory the environment happens to have.
    "-c", "safe.directory=*",
]

# Patterns the gate must match. Each is a convention actually used in this repo;
# dropping one is exactly the #61 regression.
REQUIRED_PATTERNS = [
    "*_meta_*.json",
    "*_meta.json",
    "meta_*.json",
    "*_manifest.json",
]

# Live filenames the gate is expected to discover. If a rename lands without a
# matching pattern, the first test in this file fails instead of CI quietly
# covering less.
LIVE_SAMPLES = [
    "backend/models/SPY_rf_20260524_020801_meta.json",
    "backend/models/meta_SPY.json",
    "models/DIA_meta_v1.0.json",
    "models/SPY_gbm_production_manifest.json",
    "models/IWM_gbm_wf_manifest.json",
]


# ── Harness ───────────────────────────────────────────────────────────────────
def run_gate(
    tmp_path: Path,
    subject: str = ML_SUBJECT,
    models: dict[str, dict] | None = None,
    commit: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run the gate inside an isolated copy of the repo rooted at tmp_path.

    The script derives REPO_ROOT from ``git rev-parse --show-toplevel`` and
    reads both ``models/`` and ``backend/models/``, so the fixture has to be a
    real git worktree rather than a bare directory.
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "qc" / "audit").mkdir(parents=True)
    shutil.copy2(GATE_PATH, root / "qc" / "audit" / "truth_audit.sh")

    for rel, payload in (models or {}).items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload), encoding="utf-8")

    _run(["git", "init", "-q"], cwd=root, check=True)
    _run([*GIT, "add", "-A"], cwd=root, check=True)
    if commit:
        # check=False with an explicit assert: a bare CalledProcessError here
        # says only "exit 128" and hides which git setting caused it. Surface
        # git's own stderr in the failure message instead.
        done = _run(
            [*GIT, "commit", "-q", "--allow-empty", "-m", subject],
            cwd=root, capture_output=True, text=True, check=False,
        )
        assert done.returncode == 0, (
            f"fixture git commit failed ({done.returncode}): "
            f"{done.stderr.strip() or done.stdout.strip()}"
        )
    return _gate(root)


def manifest(n_features: int, n_samples: int, sharpe=None) -> dict:
    """A *_manifest.json payload, the schema the loader can actually reaches.

    ``sharpe`` is written TOP-LEVEL on purpose. The gate's extractor reads
    ``first("sharpe", "avg_test_sharpe", "test_sharpe")`` from the document
    root and does not descend into ``metrics`` for Sharpe (it only falls back to
    ``metrics["accuracy"]``, and only under the key ``accuracy``). The real
    ``models/SPY_gbm_production_manifest.json`` has no Sharpe anywhere -- its
    ``metrics`` block holds train/test accuracy, precision, recall, f1 and
    train_samples -- so the gate correctly prints SKIP for it. A fixture that
    put Sharpe under ``metrics`` would test a schema the gate does not read.
    """
    payload = {
        "model": "gbm",
        "n_features": n_features,
        "n_samples": n_samples,
        "gate_results": {"class_balance": True},
    }
    if sharpe is not None:
        payload["sharpe"] = sharpe
    return payload


# ── Existence and syntax ──────────────────────────────────────────────────────
def test_gate_script_exists():
    assert GATE_PATH.is_file(), f"gate script missing at {GATE_PATH}"


def test_gate_is_executable():
    tracked = _run(["git", "ls-files", "--stage", "qc/audit/truth_audit.sh"],
                   cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    assert tracked.stdout.startswith("100755 "), "gate must be executable in Git for CI"


def test_gate_passes_syntax_check():
    proc = _run([_bash(), "-n", "qc/audit/truth_audit.sh"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, f"bash -n failed: {proc.stderr}"


# ── Discovery: the #61 regression ─────────────────────────────────────────────
@pytest.mark.parametrize("pattern", REQUIRED_PATTERNS)
def test_find_covers_every_metadata_convention(pattern):
    """The gate's own find must still match each convention in the repo."""
    discovered = _discovered()
    found = [line for line in discovered if Path(line).match(pattern)]
    assert found, (
        f"pattern {pattern!r} now matches nothing in the live tree. Either the "
        f"convention was renamed or the gate's find regressed to covering less."
    )


@pytest.mark.parametrize("sample", LIVE_SAMPLES)
def test_live_descriptor_is_discovered(sample):
    """Each real descriptor must be reachable by the gate's find."""
    assert (REPO_ROOT / sample).is_file(), f"fixture drifted: {sample} is gone"
    discovered = _discovered()
    assert sample in discovered, f"gate cannot see {sample}"


def test_manifest_fixtures_are_inspected(tmp_path):
    """RED for #61: a *_manifest.json must produce a verdict, not silence."""
    proc = run_gate(tmp_path, models={"models/X_manifest.json": manifest(53, 167)})
    assert "X_manifest.json" in proc.stdout, (
        "gate produced no verdict for a *_manifest.json fixture — the "
        "discovery pattern regressed to the pre-#61 state"
    )


# ── Rules 9-12: the four metric verdicts ──────────────────────────────────────
def test_ratio_violation_fails_for_ml_commit(tmp_path):
    """53 features on 167 samples is 0.317 > 0.2."""
    proc = run_gate(tmp_path, models={"models/X_manifest.json": manifest(53, 167)})
    assert "feature/sample ratio" in proc.stdout
    assert "FAIL" in proc.stdout, proc.stdout
    assert proc.returncode == 1, "a ratio violation must fail an ML-claiming commit"


def test_sharpe_ceiling_fails_for_ml_commit(tmp_path):
    proc = run_gate(
        tmp_path, models={"models/X_manifest.json": manifest(10, 1000, sharpe=8.02)}
    )
    assert "FAIL: Model models/X_manifest.json: Sharpe 8.02 > 5" in proc.stdout
    assert proc.returncode == 1, proc.stdout


def test_healthy_model_passes(tmp_path):
    """44 features on 2799 samples is 0.0157, comfortably under the ceiling."""
    proc = run_gate(tmp_path, models={"models/X_manifest.json": manifest(44, 2799)})
    assert proc.returncode == 0, proc.stdout
    assert "PASS: Model models/X_manifest.json: 2799 training samples (ok)" in proc.stdout
    assert "PASS: Model models/X_manifest.json: feature/sample ratio" in proc.stdout


def test_missing_sharpe_is_skip_not_pass(tmp_path):
    """Absent is not zero. No sharpe recorded must never score as a pass."""
    proc = run_gate(tmp_path, models={"models/X_manifest.json": manifest(44, 2799)})
    assert "SKIP" in proc.stdout, "a missing metric must print SKIP"
    assert "no Sharpe recorded" in proc.stdout


# ── The WARN/FAIL split: keep unrelated work unblocked ────────────────────────
def test_violation_warns_rather_than_fails_on_docs_commit(tmp_path):
    """A docs commit must not be blocked by pre-existing model debt.

    Enforcing rules 9-12 unconditionally would block every unrelated commit,
    which is the fastest way to get a gate switched off.
    """
    proc = run_gate(
        tmp_path, subject=DOCS_SUBJECT, models={"models/X_manifest.json": manifest(53, 167)}
    )
    assert "WARN" in proc.stdout, "violation must be surfaced as WARN"
    assert proc.returncode == 0, f"docs commit was blocked:\n{proc.stdout}"


def test_empty_tree_fails_because_nothing_was_inspected(tmp_path):
    """A gate that inspected nothing must NOT report success.

    ``truth_audit.sh`` checks that MODEL_METAS is non-empty and fails with
    "found model metadata files to inspect" otherwise. That is the right
    behaviour: an empty fixture tree is exactly the shape that let #61 hide --
    a find that matches nothing still exits 0 on a real tree full of files.
    """
    proc = run_gate(tmp_path, subject=DOCS_SUBJECT, models={})
    assert proc.returncode == 1, "gate passed having inspected zero descriptors"
    assert "found model metadata files to inspect" in proc.stdout


def test_clean_docs_commit_passes(tmp_path):
    """With a healthy descriptor present, a docs commit is not blocked."""
    proc = run_gate(
        tmp_path, subject=DOCS_SUBJECT, models={"models/X_manifest.json": manifest(44, 2799)}
    )
    assert proc.returncode == 0, proc.stdout


# ── Subject matching is scoped to the subject line, not the body ──────────────
def test_ml_word_in_body_does_not_trip_ml_rules(tmp_path):
    """The subject declares what a commit does; the body is prose.

    The script's own comment records that matching the body once made a commit
    describing model behaviour fail its own gate.
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "qc" / "audit").mkdir(parents=True)
    shutil.copy2(GATE_PATH, root / "qc" / "audit" / "truth_audit.sh")
    (root / "models").mkdir()
    (root / "models" / "X_manifest.json").write_text(
        json.dumps(manifest(53, 167)), encoding="utf-8"
    )
    _run(["git", "init", "-q"], cwd=root, check=True)
    _run([*GIT, "add", "-A"], cwd=root, check=True)
    _run(
        [*GIT, "commit", "-q", "--allow-empty", "-m",
         f"{DOCS_SUBJECT}\n\nThis note describes what the model artifacts contain."],
        cwd=root, check=True,
    )
    proc = _gate(root)
    assert proc.returncode == 0, (
        "a commit whose BODY mentions models must not be treated as ML work"
    )


@pytest.mark.parametrize("filename", ["X_meta_v1.json", "X_meta.json", "meta_X.json", "X_manifest.json"])
def test_each_convention_receives_actual_metric_verdict(tmp_path, filename):
    proc = run_gate(tmp_path, models={"models/" + filename: manifest(53, 167)})
    assert filename in proc.stdout
    assert "feature/sample ratio" in proc.stdout
    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_too_few_samples_fails(tmp_path):
    proc = run_gate(tmp_path, models={"models/X_manifest.json": manifest(1, 20)})
    assert "FAIL: Model models/X_manifest.json: only 20 training samples" in proc.stdout
    assert proc.returncode == 1, proc.stdout

def test_suspicious_accuracy_fails(tmp_path):
    data = {**manifest(10, 1000), "accuracy": 0.99}
    proc = run_gate(tmp_path, models={"models/X_manifest.json": data})
    assert "FAIL: Model models/X_manifest.json: accuracy 0.99 > 0.95" in proc.stdout
    assert proc.returncode == 1, proc.stdout
