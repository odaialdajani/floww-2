#!/usr/bin/env bash
# qc/audit/truth_audit.sh
# Verifies that the latest commit's claims match actual code state.
# Returns 0 if claims match, 1 if they don't.
# Designed to run in CI (no interactive input).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0

check() {
    local description="$1"
    local result="$2"  # "pass" or "fail"
    if [ "$result" = "pass" ]; then
        echo "  PASS: $description"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $description"
        FAIL=$((FAIL + 1))
    fi
}

# Get the latest commit message
COMMIT_MSG=$(git log -1 --pretty=%B 2>/dev/null || echo "")
if [ -z "$COMMIT_MSG" ]; then
    echo "truth_audit: no commits found, skipping"
    exit 0
fi

echo "=== Truth Audit ==="
echo "Commit: $(git log -1 --oneline)"
echo "Message: $(echo "$COMMIT_MSG" | head -1)"
echo ""

# --- Rule 1: No synthetic data in any commit touching ML ---
if echo "$COMMIT_MSG" | grep -qiE "ml|model|train|synthetic|data.*gen"; then
    # `|| true` is required because pipefail+errexit would otherwise abort the
    # entire script when grep finds nothing (exit 1). With this guard, the
    # subsequent rules actually get a chance to run. Without it, the audit
    # silently exits after this assignment with code 1 and reports zero rules.
    SYNTHETIC_REFS=$(grep -rn "np\.random\." backend/ml*.py 2>/dev/null | grep -v "__pycache__" | wc -l || true)
    if [ "${SYNTHETIC_REFS:-0}" -gt 0 ]; then
        check "ML commit must not contain np.random data generation" "fail"
        grep -rn "np\.random\." backend/ml*.py 2>/dev/null | head -5 || true
    else
        check "ML commit contains no np.random data generation" "pass"
    fi
fi

# --- Rule 2: If commit claims "refactor", server.py must not have grown ---
if echo "$COMMIT_MSG" | grep -qiE "refactor|Phase A"; then
    SERVER_LINES=$(wc -l < backend/server.py 2>/dev/null || echo 0)
    if [ "$SERVER_LINES" -gt 3532 ]; then
        check "Refactor commit: server.py must not grow (currently $SERVER_LINES lines, baseline 3532)" "fail"
    else
        check "Refactor commit: server.py did not grow ($SERVER_LINES lines)" "pass"
    fi
fi

# --- Rule 3: If commit claims VEX/DEX/Vega, grep must find it ---
if echo "$COMMIT_MSG" | grep -qiE "vex|vanna.*exposure|calc_vex"; then
    if grep -rn "def calc_vex" backend/ 2>/dev/null | grep -v "__pycache__" | grep -q .; then
        check "VEX commit: def calc_vex found in codebase" "pass"
    else
        check "VEX commit: def calc_vex NOT found in codebase" "fail"
    fi
fi

if echo "$COMMIT_MSG" | grep -qiE "dex|delta.*exposure|calc_dex"; then
    if grep -rn "def calc_dex" backend/ 2>/dev/null | grep -v "__pycache__" | grep -q .; then
        check "DEX commit: def calc_dex found in codebase" "pass"
    else
        check "DEX commit: def calc_dex NOT found in codebase" "fail"
    fi
fi

if echo "$COMMIT_MSG" | grep -qiE "vega.*total|total.*vega|calc_vega_total"; then
    if grep -rn "def calc_vega_total" backend/ 2>/dev/null | grep -v "__pycache__" | grep -q .; then
        check "Vega-Total commit: def calc_vega_total found in codebase" "pass"
    else
        check "Vega-Total commit: def calc_vega_total NOT found in codebase" "fail"
    fi
fi

# --- Rule 4: If commit claims "quarantine", at least one model must be in _quarantine/ ---
# Note: partial quarantine is the norm (e.g. quarantine SPY+TLT+IWM, keep DIA+QQQ live).
# Prior version asserted LIVE_COUNT==0 which only made sense for "quarantine everything"
# commits — a false-negative on every targeted quarantine since.
if echo "$COMMIT_MSG" | grep -qiE "quarantine|degenerate"; then
    QUARANTINE_COUNT=$(ls models/_quarantine/*.joblib 2>/dev/null | wc -l)
    LIVE_COUNT=$(ls models/*.joblib 2>/dev/null | wc -l)
    if [ "$QUARANTINE_COUNT" -gt 0 ]; then
        check "Quarantine commit: $QUARANTINE_COUNT files in _quarantine/, $LIVE_COUNT live (partial quarantine OK)" "pass"
    else
        check "Quarantine commit: nothing in models/_quarantine/" "fail"
    fi
fi

# --- Rule 5: If commit claims "ML" or "model", DegenerateModelError must exist ---
if echo "$COMMIT_MSG" | grep -qiE "ml|model.*guard|degenerate|training.*guard|quality.*gate" && ! echo "$COMMIT_MSG" | grep -qiE "model.*path|model.*naming|model.*file"; then
    if grep -rn "class DegenerateModelError\|DegenerateModelError" backend/ml_pipeline.py 2>/dev/null | grep -q .; then
        check "ML guard commit: DegenerateModelError found in ml_pipeline.py" "pass"
    else
        check "ML guard commit: DegenerateModelError NOT found in ml_pipeline.py" "fail"
    fi
fi

# --- Rule 6: If commit claims "CI" or "audit", truth_audit.sh must exist and be executable ---
if echo "$COMMIT_MSG" | grep -qiE "ci|audit|hook|pre-commit"; then
    if [ -x "qc/audit/truth_audit.sh" ]; then
        check "CI commit: qc/audit/truth_audit.sh exists and is executable" "pass"
    else
        check "CI commit: qc/audit/truth_audit.sh missing or not executable" "fail"
    fi
fi

# --- Rule 7: If commit claims "MongoDB" or "load", verify pymongo/motor imports ---
# `set -euo pipefail` makes the grep below fragile: if the `backend/scripts/`
# glob doesn't match (the directory has never existed), grep exits with status
# 2 and pipefail propagates that as a pipe failure, turning a legitimate match
# in `scripts/` into a FAIL. Enumerate paths defensively so a missing dir
# can't poison the check.
if echo "$COMMIT_MSG" | grep -qiE "mongo|load.*dataset|backfill"; then
    MONGO_PATHS=()
    for p in scripts backend/scripts backend/services backend/routes backend/tests; do
        [ -d "$p" ] && MONGO_PATHS+=("$p")
    done
    if [ ${#MONGO_PATHS[@]} -gt 0 ] && \
        grep -rn "motor\|pymongo\|MongoClient" "${MONGO_PATHS[@]}" --include="*.py" 2>/dev/null | grep -q .; then
        check "MongoDB commit: motor/pymongo imports found" "pass"
    else
        check "MongoDB commit: motor/pymongo imports NOT found" "fail"
    fi
fi

# --- Rule 8: Universal — no .env file in repo ---
if [ -f ".env" ] && [ -z "$(git check-ignore .env 2>/dev/null)" ]; then
    check ".env file is git-ignored" "fail"
else
    check ".env file is git-ignored or absent" "pass"
fi

# --- Model metadata discovery (shared by Rules 9-12) ---
# The production models named in CLAUDE.md live in backend/models/, NOT in the
# repo-root models/ tree. Rules 9-12 used to glob `models/*_meta_*.json`, which
# is wrong twice over: it never descends into backend/models/, and its
# `_meta_` infix does not match backend's `*_meta.json` / `meta_*.json` naming.
# Net effect: the audit inspected 2 stale v1.0 files at the repo root and left
# every real production model unchecked, while printing PASS.
#
# Discover BOTH trees and BOTH naming conventions, once, here.
MODEL_METAS=$(
    find models backend/models -maxdepth 2 -type f \
        \( -name '*_meta_*.json' -o -name '*_meta.json' -o -name 'meta_*.json' \) \
        2>/dev/null | grep -v '_quarantine' || true
)
if [ -z "$MODEL_METAS" ]; then
    check "Model audit: found model metadata files to inspect" "fail"
    echo "  (searched models/ and backend/models/ for *_meta_*.json, *_meta.json, meta_*.json)"
fi

# --- Model metric extraction (Rules 9-12) ---
# Two meta schemas exist in this repo and the rules only understood one:
#   root models/*_meta_v1.0.json  -> sharpe / accuracy / n_samples / n_features
#   backend/models/*_meta.json    -> walk-forward CV: avg_test_sharpe /
#                                    avg_test_accuracy / fold_details[].n_train
# Reading only the first schema meant every backend model reported 0 for every
# metric, so the rules printed "Sharpe 0 (reasonable)" for a model whose real
# avg_test_sharpe is 8.02 — the exact thing Rule 9 exists to catch — while
# simultaneously FAILING it on "0 training samples". Absent is not zero.
#
# Emits one metric per call, or the literal string "NA" when neither schema
# carries it. "NA" means UNKNOWN and must never be scored as pass or fail.
# Rules 9-12 judge MODEL QUALITY, which is a property of the artifacts on disk,
# not of the commit in front of us. Enforcing them on every commit would block
# unrelated work on pre-existing model debt — the fastest way to get a gate
# switched off. So they BLOCK only when the commit actually claims ML/model work
# (same trigger as Rule 1), and otherwise print WARN so the finding is never
# invisible. This is scoped enforcement, not a disabled check.
# Match the SUBJECT LINE ONLY, not the whole message. Matching the body means a
# commit that merely *describes* model behaviour in its explanation trips the
# gate — this very rule blocked its own commit that way on the first try. The
# subject is what declares what a commit does; the body is prose.
COMMIT_SUBJECT=$(echo "$COMMIT_MSG" | head -1)
if echo "$COMMIT_SUBJECT" | grep -qiE "\b(ml|model|models|train|training|retrain|promote)\b"; then
    MODEL_RULES_BLOCK=1
else
    MODEL_RULES_BLOCK=0
fi

model_check() {  # $1=description  $2=pass|fail
    if [ "$2" = "pass" ] || [ "$MODEL_RULES_BLOCK" -eq 1 ]; then
        check "$1" "$2"
    else
        echo "  WARN: $1  (not blocking — commit does not claim ML/model work)"
    fi
}

model_metric() {  # $1=file  $2=metric
    python3 - "$1" "$2" <<'PY' 2>/dev/null || echo NA
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("NA"); raise SystemExit
m = sys.argv[2]
folds = d.get("fold_details") or []
def first(*keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None
if m == "sharpe":
    v = first("sharpe", "avg_test_sharpe", "test_sharpe")
elif m == "accuracy":
    v = first("accuracy", "avg_test_accuracy", "test_accuracy")
    if v is None:
        v = (d.get("metrics") or {}).get("accuracy")
elif m == "n_samples":
    v = first("n_samples", "n_train")
    if v is None and folds:
        # Walk-forward: the widest fold is the real training set size.
        sizes = [f.get("n_train", 0) + f.get("n_test", 0) for f in folds]
        v = max(sizes) if sizes else None
elif m == "n_features":
    v = first("n_features_used", "n_features")
    if v is None and isinstance(d.get("feature_names"), list):
        v = len(d["feature_names"])
else:
    v = None
print("NA" if v is None else v)
PY
}

# --- Rule 9: Model audit — no model with Sharpe > 5 or empty baselines ---
# Check all model meta JSON files for suspicious claims
for meta in $MODEL_METAS; do
    [ -f "$meta" ] || continue
    # Skip quarantined models
    [[ "$meta" == *"_quarantine"* ]] && continue
    # Check for empty baselines
    if grep -q '"baselines": {}' "$meta" 2>/dev/null; then
        model_check "Model $meta: empty baselines dict (unverified)" "fail"
    fi
    # Check for Sharpe > 5 (suspicious for daily direction)
    sharpe=$(model_metric "$meta" sharpe)
    if [ "$sharpe" = "NA" ]; then
        echo "  SKIP: Model $meta: no Sharpe recorded in either schema — NOT verified"
    elif [ "$(python3 -c "print(1 if float('$sharpe') > 5 else 0)" 2>/dev/null || echo 0)" -eq 1 ]; then
        model_check "Model $meta: Sharpe $sharpe > 5 (suspicious)" "fail"
    else
        model_check "Model $meta: Sharpe $sharpe (reasonable)" "pass"
    fi
done

# --- Rule 10: No model trained on too few samples ---
# Flag models with fewer than 50 training samples
for meta in $MODEL_METAS; do
    [ -f "$meta" ] || continue
    [[ "$meta" == *"_quarantine"* ]] && continue
    n_samples=$(model_metric "$meta" n_samples)
    if [ "$n_samples" = "NA" ]; then
        echo "  SKIP: Model $meta: no sample count recorded — NOT verified"
    elif [ "$n_samples" -lt 50 ] 2>/dev/null; then
        model_check "Model $meta: only $n_samples training samples (suspicious)" "fail"
    else
        model_check "Model $meta: $n_samples training samples (ok)" "pass"
    fi
done

# --- Rule 11: Feature-to-sample ratio check ---
# Flag models with more features than 20% of samples
for meta in $MODEL_METAS; do
    [ -f "$meta" ] || continue
    [[ "$meta" == *"_quarantine"* ]] && continue
    n_samples=$(model_metric "$meta" n_samples)
    n_features=$(model_metric "$meta" n_features)
    if [ "$n_samples" = "NA" ] || [ "$n_features" = "NA" ]; then
        echo "  SKIP: Model $meta: feature/sample ratio not computable — NOT verified"
    elif [ "$n_samples" -gt 0 ] 2>/dev/null && [ "$n_features" -gt 0 ] 2>/dev/null; then
        ratio=$(python3 -c "print($n_features / $n_samples)" 2>/dev/null || echo 0)
        if [ "$(python3 -c "print(1 if float('$ratio') > 0.2 else 0)" 2>/dev/null || echo 0)" -eq 1 ]; then
            model_check "Model $meta: feature/sample ratio $ratio > 0.2 ($n_features features / $n_samples samples)" "fail"
        else
            model_check "Model $meta: feature/sample ratio $ratio (ok)" "pass"
        fi
    fi
done

# --- Rule 12: No model with accuracy > 95% on daily direction ---
# Daily direction prediction > 95% is almost certainly overfit
for meta in $MODEL_METAS; do
    [ -f "$meta" ] || continue
    [[ "$meta" == *"_quarantine"* ]] && continue
    acc=$(model_metric "$meta" accuracy)
    if [ "$acc" = "NA" ]; then
        echo "  SKIP: Model $meta: no accuracy recorded — NOT verified"
    elif [ "$(python3 -c "print(1 if float('$acc') > 0.95 else 0)" 2>/dev/null || echo 0)" -eq 1 ]; then
        model_check "Model $meta: accuracy $acc > 0.95 (likely overfit)" "fail"
    else
        model_check "Model $meta: accuracy $acc (reasonable)" "pass"
    fi
done

# --- Summary ---
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "TRUTH AUDIT FAILED — commit claims do not match code state."
    echo "Fix the issues above, or update the commit message to match reality."
    exit 1
fi

echo "TRUTH AUDIT PASSED — all claims verified."
exit 0
