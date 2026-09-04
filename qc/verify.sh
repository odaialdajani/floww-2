#!/usr/bin/env bash
# Verification script for Confluence Decoder
# Run: bash qc/verify.sh
#
# Every Python tool runs through the project interpreter as a module
# (python -m <tool>), so this works with either virtualenv layout —
# POSIX (.venv/bin/python) or Windows (.venv313/Scripts/python.exe).
#
# HONEST-VERDICT CONTRACT
# ----------------------
# A check that did not run is NEVER allowed to look like a pass, and the
# LAST LINE of this script can never say "green" unless every gating check
# actually executed and succeeded.  Each section records exactly one of:
#
#   PASS      the check ran and succeeded                 (gating)
#   FAIL      the check ran and failed                    (gating -> exit 1)
#   SKIP      the check could NOT run here                (-> exit 2)
#   ADVISORY  the check ran, reported findings, non-gating (exit unchanged)
#   N/A       the check does not exist in this repo by design (not a skip)
#
# Exit codes:
#   0  every gating check ran and passed (advisories may exist)
#   1  at least one gating check FAILED
#   2  nothing failed, but at least one check was SKIPPED — the repo was
#      only PARTIALLY verified.  Treat 2 as "unknown", not as "good".
#
# No single section may abort the run.  Every command that can fail is
# evaluated inside an `if`, so `set -e` never short-circuits the sweep and
# a developer with zero tooling installed still gets a complete report of
# what was and was not checked.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# --- result accounting ----------------------------------------------------
# Newline-delimited strings, not arrays: `${#arr[@]}` on an empty array is an
# unbound-variable error under `set -u` in bash 3.2 (still the system bash on
# macOS), and this script has to survive there too.
N_PASS=0
N_FAIL=0
N_SKIP=0
N_ADVISORY=0
N_NA=0
LIST_FAIL=""
LIST_SKIP=""
LIST_ADVISORY=""
LIST_NA=""
NL="
"

ok() {        # ok <check-name>
    echo "PASS: $1"
    N_PASS=$((N_PASS + 1))
}
bad() {       # bad <check-name> <why>
    echo "FAIL: $1 — $2"
    N_FAIL=$((N_FAIL + 1))
    LIST_FAIL="${LIST_FAIL}  - $1 — $2${NL}"
}
skip() {      # skip <check-name> <why-it-could-not-run>
    echo "SKIP: $1 — $2"
    N_SKIP=$((N_SKIP + 1))
    LIST_SKIP="${LIST_SKIP}  - $1 — $2${NL}"
}
advisory() {  # advisory <check-name> <what-it-reported>
    echo "ADVISORY: $1 — $2"
    N_ADVISORY=$((N_ADVISORY + 1))
    LIST_ADVISORY="${LIST_ADVISORY}  - $1 — $2${NL}"
}
na() {        # na <check-name> <why-it-does-not-apply>
    echo "N/A: $1 — $2"
    N_NA=$((N_NA + 1))
    LIST_NA="${LIST_NA}  - $1 — $2${NL}"
}

# --- resolve the backend interpreter -------------------------------------
BACKEND_PY=""
for _candidate in \
    backend/.venv313/Scripts/python.exe \
    backend/.venv313/bin/python \
    backend/.venv/Scripts/python.exe \
    backend/.venv/bin/python; do
    if [ -x "$_candidate" ]; then
        BACKEND_PY="$PWD/$_candidate"
        break
    fi
done
if [ -z "$BACKEND_PY" ]; then
    echo "FATAL: no backend virtualenv interpreter found. Looked for:"
    echo "  backend/.venv313/Scripts/python.exe   (Windows)"
    echo "  backend/.venv313/bin/python           (POSIX)"
    echo "  backend/.venv/Scripts/python.exe      (Windows)"
    echo "  backend/.venv/bin/python              (POSIX)"
    echo ""
    echo "=== VERIFY ABORTED: nothing was checked ==="
    exit 1
fi

echo "=== Interpreter ==="
echo "$BACKEND_PY"
"$BACKEND_PY" --version

# has_module <import-name> — true when the tool is importable in BACKEND_PY
has_module() { "$BACKEND_PY" -c "import $1" >/dev/null 2>&1; }

echo ""
echo "=== Pre-commit ==="
# This repo's .pre-commit-config.yaml has exactly ONE hook, `consolidate-diff`,
# which shells out to `make consolidate-diff` and exits non-zero whenever the
# regenerated reports/agentfield_consolidated_diff_*.md bytes drift from what
# is on disk.  That is a normal, expected outcome — it means "regenerate and
# restage the report", not "the code is broken".  Running it bare under
# `set -e` therefore aborted this whole script in its FIRST section on any
# machine that had pre-commit installed.  It is now reported and survived.
if ! command -v pre-commit >/dev/null 2>&1; then
    skip "pre-commit" "pre-commit is not on PATH (install: pip install pre-commit)"
elif [ ! -f .pre-commit-config.yaml ]; then
    skip "pre-commit" "no .pre-commit-config.yaml at the repo root"
elif pre-commit run --all-files; then
    ok "pre-commit"
else
    bad "pre-commit" "a hook exited non-zero (the only hook here is consolidate-diff via 'make consolidate-diff'; if the report bytes drifted, regenerate and 'git add' reports/agentfield_consolidated_diff_*.md, then re-run)"
fi

echo ""
echo "=== Ruff lint ==="
if ! has_module ruff; then
    skip "ruff lint" "ruff is NOT installed in this virtualenv. Config lives in backend/pyproject.toml; CI pins ruff==0.15.22 (.github/workflows/lint.yml). Match CI locally with: $BACKEND_PY -m pip install 'ruff==0.15.22'"
elif (cd backend && "$BACKEND_PY" -m ruff check .); then
    ok "ruff lint"
else
    bad "ruff lint" "ruff check reported violations (see output above)"
fi

echo ""
echo "=== Ruff format check ==="
if ! has_module ruff; then
    skip "ruff format check" "ruff is NOT installed in this virtualenv (same install line as above)"
elif (cd backend && "$BACKEND_PY" -m ruff format --check .); then
    ok "ruff format check"
else
    bad "ruff format check" "files are not ruff-formatted (run: $BACKEND_PY -m ruff format .)"
fi

echo ""
echo "=== MyPy ==="
if ! has_module mypy; then
    skip "mypy" "mypy is NOT installed in this virtualenv (install: $BACKEND_PY -m pip install mypy)"
elif (cd backend && "$BACKEND_PY" -m mypy . --ignore-missing-imports); then
    ok "mypy"
else
    # Advisory by long-standing project policy: type findings are reported,
    # they do not gate this script.  They ARE named in the summary.
    advisory "mypy" "reported type issues (non-blocking)"
fi

echo ""
echo "=== Bandit security ==="
if ! has_module bandit; then
    skip "bandit" "bandit is NOT installed in this virtualenv (install: $BACKEND_PY -m pip install bandit)"
elif (cd backend && "$BACKEND_PY" -m bandit -r . -ll -ii); then
    ok "bandit"
else
    advisory "bandit" "reported security findings (non-blocking)"
fi

echo ""
echo "=== pip-audit ==="
if ! has_module pip_audit; then
    skip "pip-audit" "pip-audit is NOT installed in this virtualenv (install: $BACKEND_PY -m pip install pip-audit)"
elif (cd backend && "$BACKEND_PY" -m pip_audit -r requirements.txt); then
    ok "pip-audit"
else
    advisory "pip-audit" "reported vulnerable pins in backend/requirements.txt (non-blocking)"
fi

echo ""
echo "=== Pytest ==="
echo "NOTE: the backend suite needs MongoDB listening on localhost:27017 —"
echo "      backend/tests/conftest.py opens a Motor client per test."
if "$BACKEND_PY" -c "
import socket, sys
s = socket.socket(); s.settimeout(2)
try:
    s.connect(('127.0.0.1', 27017))
except OSError:
    sys.exit(1)
finally:
    s.close()
" >/dev/null 2>&1; then
    if (cd backend && "$BACKEND_PY" -m pytest tests/ -v --tb=short 2>&1 | tail -20); then
        ok "backend pytest (full suite)"
    else
        bad "backend pytest (full suite)" "one or more tests failed (see tail above)"
    fi
else
    skip "backend pytest (full suite)" "MongoDB is not reachable on localhost:27017 — the real pass count is UNKNOWN. Start mongod and re-run."
    echo "      Falling back to a collection-only smoke check (no DB needed):"
    # Collection is a genuine, gating check on its own: it proves every test
    # module imports.  It does NOT substitute for running the suite.
    if (cd backend && "$BACKEND_PY" -m pytest --collect-only -q 2>&1 | tail -3); then
        ok "backend pytest (collection-only smoke)"
    else
        bad "backend pytest (collection-only smoke)" "pytest could not collect the suite"
    fi
fi

echo ""
echo "=== Frontend lint ==="
# Genuinely N/A, not skipped: there is no lint step in this repo to run.
# frontend/package.json defines only start / build / test, and ESLint is
# deliberately stripped from the webpack pipeline in frontend/craco.config.js
# (ESLintWebpackPlugin + eslint-loader removed).  Both files are
# architect-frozen, so the build below is the frontend gate.
na "frontend lint" "no lint step exists in this repo — package.json has no lint script and ESLint is stripped from craco.config.js (both architect-frozen); the frontend build is the gate"

echo ""
echo "=== Frontend build ==="
if ! command -v npx >/dev/null 2>&1; then
    skip "frontend build" "npx is not on PATH (install Node.js)"
elif [ ! -d frontend/node_modules ]; then
    skip "frontend build" "frontend/node_modules is missing (run: cd frontend && npm install)"
elif (cd frontend && npx craco build 2>&1 | tail -12); then
    ok "frontend build"
else
    bad "frontend build" "npx craco build exited non-zero (see tail above)"
fi

# --- verdict --------------------------------------------------------------
N_RAN=$((N_PASS + N_FAIL + N_ADVISORY))
N_TOTAL=$((N_RAN + N_SKIP))

echo ""
echo "=== Summary ==="
echo "  passed:   $N_PASS"
echo "  failed:   $N_FAIL"
echo "  skipped:  $N_SKIP"
echo "  advisory: $N_ADVISORY"
echo "  n/a:      $N_NA"

if [ "$N_FAIL" -gt 0 ]; then
    echo ""
    echo "FAILED checks:"
    printf '%s' "$LIST_FAIL"
fi
if [ "$N_SKIP" -gt 0 ]; then
    echo ""
    echo "SKIPPED checks — these were NOT verified:"
    printf '%s' "$LIST_SKIP"
fi
if [ "$N_ADVISORY" -gt 0 ]; then
    echo ""
    echo "ADVISORY checks — ran, reported findings, did not gate this run:"
    printf '%s' "$LIST_ADVISORY"
fi
if [ "$N_NA" -gt 0 ]; then
    echo ""
    echo "N/A checks — nothing to run in this repo by design:"
    printf '%s' "$LIST_NA"
fi

echo ""
echo "Exit codes: 0 = all $N_TOTAL checks ran and passed | 1 = a check FAILED |"
echo "            2 = no failures, but some checks were SKIPPED (partial verification)"
echo ""

if [ "$N_FAIL" -gt 0 ]; then
    echo "=== VERIFY FAILED: $N_FAIL of $N_TOTAL checks failed, $N_SKIP skipped — NOT GREEN ==="
    exit 1
fi
if [ "$N_SKIP" -gt 0 ]; then
    echo "=== VERIFY INCOMPLETE: only $N_RAN of $N_TOTAL checks ran — $N_SKIP SKIPPED, so this repo is NOT verified. This is NOT a green run. ==="
    exit 2
fi
if [ "$N_ADVISORY" -gt 0 ]; then
    echo "=== VERIFY GREEN (all $N_TOTAL checks ran; $N_ADVISORY advisory finding(s) reported above) ==="
    exit 0
fi
echo "=== ALL GREEN: all $N_TOTAL checks ran and passed ==="
exit 0
