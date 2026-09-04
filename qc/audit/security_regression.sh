#!/usr/bin/env bash
# qc/audit/security_regression.sh
# Regression tests for CRITICAL security findings.
# Run after any security fix to verify the fix holds.
#
# Portable by design: the repo root comes from git, every path below is
# relative to it, and any check that cannot actually run on this platform
# prints SKIP.  A check that did not run must never score as PASS.
#
# HONEST-VERDICT CONTRACT (same standard as qc/verify.sh)
# ------------------------------------------------------
#   PASS  the check ran and the property holds
#   FAIL  the check ran and the property is violated   -> exit 1
#   SKIP  the check could NOT run here                 -> exit 2
#   N/A   the property cannot exist on this platform (e.g. POSIX mode bits
#         on NTFS) — structurally inapplicable, not "unverified"
#
# Exit codes:
#   0  every check ran and passed
#   1  at least one check FAILED
#   2  nothing failed, but at least one check was SKIPPED — the security
#      posture is only PARTIALLY verified.  Treat 2 as "unknown", not "good".
#
# Test seam: set SECURITY_REGRESSION_AUTH_FILE=<path> to point the C-02
# fail-closed assertion at a scratch copy of auth.py.  That is how the
# positive control is proved (mutate the copy, the check must flip to FAIL).
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

UNAME_S="$(uname -s 2>/dev/null || echo unknown)"

PASS=0
FAIL=0
SKIP=0
NA=0
LIST_FAIL=""
LIST_SKIP=""
LIST_NA=""
NL="
"

# NOTE: use `X=$((X + 1))`, never `((X++))`.  Under `set -e`, `((0++))`
# evaluates to 0, which bash reports as exit status 1 and kills the script
# on the very first successful check.
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); LIST_FAIL="${LIST_FAIL}  - $1${NL}"; }
skip() { echo "  SKIP: $1"; SKIP=$((SKIP + 1)); LIST_SKIP="${LIST_SKIP}  - $1${NL}"; }
na()   { echo "  N/A:  $1"; NA=$((NA + 1));     LIST_NA="${LIST_NA}  - $1${NL}"; }

check() {
    local label="$1"
    shift
    if "$@" &>/dev/null; then
        pass "$label"
    else
        fail "$label"
    fi
}

check_not() {
    local label="$1"
    shift
    if "$@" &>/dev/null; then
        fail "$label (expected failure but succeeded)"
    else
        pass "$label"
    fi
}

# Backend interpreter — Windows venv layout first, then POSIX.
BACKEND_PY=""
for _candidate in \
    backend/.venv313/Scripts/python.exe \
    backend/.venv313/bin/python \
    backend/.venv/Scripts/python.exe \
    backend/.venv/bin/python; do
    if [ -x "$_candidate" ]; then
        BACKEND_PY="$_candidate"
        break
    fi
done

echo "=== Security Regression Tests ==="
echo "Repo root: $REPO_ROOT"

# C-01: .env file permissions must be 0600 or more restrictive
echo ""
echo "--- C-01: .env file permissions ---"
if [ ! -f backend/.env ]; then
    skip "C-01 .env permissions — backend/.env not found, nothing to inspect"
else
    case "$UNAME_S" in
        MINGW*|MSYS*|CYGWIN*)
            # NTFS has no POSIX mode bits; stat(1) reports a synthetic 644 for
            # every file, so a permission assertion here would be meaningless.
            na "C-01 .env permissions — POSIX mode bits do not exist on Windows/NTFS"
            ;;
        *)
            ENV_PERMS=""
            if ENV_PERMS=$(stat -c "%a" backend/.env 2>/dev/null); then
                :   # GNU coreutils
            elif ENV_PERMS=$(stat -f "%Lp" backend/.env 2>/dev/null); then
                :   # BSD / macOS
            else
                ENV_PERMS=""
            fi
            if [ -z "$ENV_PERMS" ]; then
                skip "C-01 .env permissions — no usable stat(1) on this platform"
            else
                case "$ENV_PERMS" in
                    [0246]00)
                        pass "C-01 .env permissions are 0600 or stricter (found 0$ENV_PERMS)"
                        ;;
                    *)
                        fail "C-01 .env permissions are 0$ENV_PERMS (want 0600 or stricter)"
                        ;;
                esac
            fi
            ;;
    esac
fi

# C-02: Auth must fail closed when API_SECRET_KEY is unset
echo ""
echo "--- C-02: Auth fail-closed ---"
#
# The old check was near-vacuous: it grepped for the literal source text
# "if not expected_key" and counted "return True" in the next 3 lines.  Two
# ways to score a PASS with broken auth:
#   1. write the bypass any other way (the literal never appears), or
#   2. DELETE the fail-closed guard entirely — no grep hits means no
#      "return True" hits, which the old logic read as clean.
# Deletion is the dangerous one: with the guard gone, an unset API_SECRET_KEY
# makes expected_key "" and hmac.compare_digest("", "") returns True, so every
# mutating route becomes open.
#
# The check below is therefore POSITIVE: it parses auth.py's indentation and
# asserts that require_api_key and verify_api_key EACH still contain an
# `if not expected_key:` block that raises HTTPException with 503 — and that
# no such block anywhere in the file returns True.  Removing a guard now FAILS.
C02_AWK='
function indent_of(s,   i, c, n) {
    n = 0
    for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        if (c == " " || c == "\t") { n++ } else { break }
    }
    return n
}
BEGIN {
    nreq = split("require_api_key verify_api_key", req, " ")
    fn = "<module>"
    inblk = 0
    gind = 0
}
{ line = $0 }
inblk == 1 {
    if (line ~ /^[[:space:]]*$/) { next }
    if (indent_of(line) > gind) { body[fn] = body[fn] " " line; next }
    inblk = 0
}
line ~ /^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+/ {
    f = line
    sub(/^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+/, "", f)
    sub(/[(].*$/, "", f)
    fn = f
    next
}
line ~ /^[[:space:]]*if[[:space:]]+not[[:space:]]+expected_key[[:space:]]*:/ {
    guard[fn] = 1
    gind = indent_of(line)
    inblk = 1
    next
}
END {
    bad = 0
    # Negative half: no unset-key branch anywhere may return True.
    for (f in guard) {
        if (body[f] ~ /return[[:space:]]+True/) {
            printf "OPEN_BYPASS   %s : unset-key branch returns True\n", f
            bad = 1
        }
    }
    # Positive half: both auth entrypoints must still fail closed with 503.
    for (i = 1; i <= nreq; i++) {
        f = req[i]
        if (!(f in guard)) {
            printf "MISSING_GUARD %s : no unset-key fail-closed guard found\n", f
            bad = 1
            continue
        }
        if (body[f] !~ /raise[[:space:]]+HTTPException/) {
            printf "NO_RAISE      %s : guard does not raise HTTPException\n", f
            bad = 1
            continue
        }
        if (body[f] !~ /503/) {
            printf "NO_503        %s : guard raises, but not with status 503\n", f
            bad = 1
            continue
        }
        printf "OK            %s : fail-closed guard raises HTTPException 503\n", f
    }
    exit bad
}
'
AUTH_FILE="${SECURITY_REGRESSION_AUTH_FILE:-backend/auth.py}"
echo "  auth source: $AUTH_FILE"
if [ ! -f "$AUTH_FILE" ]; then
    fail "C-02 auth fail-closed — $AUTH_FILE not found"
elif ! command -v awk >/dev/null 2>&1; then
    skip "C-02 auth fail-closed — awk is not available on this platform"
else
    C02_RC=0
    C02_OUT=$(awk "$C02_AWK" "$AUTH_FILE") || C02_RC=$?
    if [ -n "$C02_OUT" ]; then
        printf '%s\n' "$C02_OUT" | sed 's/^/    /'
    fi
    if [ "$C02_RC" -eq 0 ]; then
        pass "C-02 auth fails closed — require_api_key and verify_api_key both raise HTTPException 503 when API_SECRET_KEY is unset"
    else
        fail "C-02 auth does NOT fail closed — see the diagnostic lines above"
    fi
fi

# C-03: WebSocket endpoints must require auth
echo ""
echo "--- C-03: WebSocket auth ---"
# Check that WS endpoints have auth check before accept()
if [ ! -f backend/server.py ]; then
    fail "C-03 backend/server.py not found — cannot verify WebSocket auth"
else
    WS_AUTH=$(grep -A5 "websocket_endpoint\|websocket_gex" backend/server.py 2>/dev/null | grep -c "token\|auth\|api_key\|close(code=" || true)
    if [ "${WS_AUTH:-0}" -gt 0 ]; then
        pass "C-03 WebSocket endpoints have auth check"
    else
        fail "C-03 WebSocket endpoints have no auth check"
    fi
fi

# C-04: Dash UI must have access control
echo ""
echo "--- C-04: Dash UI access control ---"
if [ ! -f backend/server.py ]; then
    fail "C-04 backend/server.py not found — cannot verify Dash UI access control"
elif grep -q "dash_auth\|DASH_SESSION\|dashboard.*auth\|dashboard.*token" backend/server.py 2>/dev/null; then
    pass "C-04 Dash UI has access control"
else
    fail "C-04 Dash UI has no access control"
fi

# C-05: CORS must not default to wildcard in production
echo ""
echo "--- C-05: CORS no wildcard default ---"
if [ ! -f backend/server.py ]; then
    fail "C-05 backend/server.py not found — cannot verify CORS default"
else
    # Read the CORS block once, then reason about it — the old single-line
    # regexes matched nothing at all, so this check always fell through to a
    # vacuous PASS.
    CORS_CTX=$(grep -A20 'os.environ.get("CORS_ORIGINS"' backend/server.py 2>/dev/null || true)
    if [ -z "$CORS_CTX" ]; then
        fail "C-05 no CORS_ORIGINS handling found in server.py"
    elif printf '%s\n' "$CORS_CTX" | grep -q '\["\*"\]'; then
        # A wildcard fallback exists — it must be gated by a startup abort.
        if printf '%s\n' "$CORS_CTX" | grep -qE 'raise (RuntimeError|ValueError)|CORS_ORIGINS must be set'; then
            pass "C-05 CORS has production guard"
        else
            fail "C-05 CORS defaults to wildcard without guard"
        fi
    else
        pass "C-05 CORS does not default to wildcard"
    fi
fi

# H-03: POST routes should use Pydantic models (not Dict[str, Any])
echo ""
echo "--- H-03: POST routes use Pydantic models ---"
# `grep -c` over a glob prints one "file:count" line PER FILE, so the old
# scalar comparison blew up on 55 lines of output.  Count matching files.
RAW_DICT_ROUTES=$(grep -l "Dict\[str, Any\]" backend/routes/*.py 2>/dev/null | wc -l | tr -d '[:space:]' || true)
if [ "${RAW_DICT_ROUTES:-0}" -eq 0 ]; then
    pass "H-03 No routes accept raw Dict[str, Any]"
else
    fail "H-03 $RAW_DICT_ROUTES route module(s) still accept raw Dict[str, Any]"
fi

# H-06: pymongo version
echo ""
echo "--- H-06: pymongo version ---"
if [ -z "$BACKEND_PY" ]; then
    skip "H-06 pymongo >= 4.6.3 — no backend virtualenv interpreter found"
else
    PYMONGO_VER=$("$BACKEND_PY" -c "import pymongo; print(pymongo.__version__)" 2>/dev/null || echo "unknown")
    check "H-06 pymongo >= 4.6.3 (found $PYMONGO_VER)" "$BACKEND_PY" -c "
from packaging.version import Version
import pymongo
assert Version(pymongo.__version__) >= Version('4.6.3'), f'pymongo {pymongo.__version__} < 4.6.3'
"
fi

# --- verdict --------------------------------------------------------------
RAN=$((PASS + FAIL))
TOTAL=$((RAN + SKIP))

echo ""
echo "=== Results: $PASS passed, $FAIL failed, $SKIP skipped, $NA n/a ==="

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "FAILED checks:"
    printf '%s' "$LIST_FAIL"
fi
if [ "$SKIP" -gt 0 ]; then
    echo ""
    echo "SKIPPED checks — these security properties were NOT verified:"
    printf '%s' "$LIST_SKIP"
fi
if [ "$NA" -gt 0 ]; then
    echo ""
    echo "N/A checks — the property cannot exist on this platform:"
    printf '%s' "$LIST_NA"
fi

echo ""
echo "Exit codes: 0 = all $TOTAL checks ran and passed | 1 = a check FAILED |"
echo "            2 = no failures, but some checks were SKIPPED (partial verification)"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo "SECURITY REGRESSION FAILED: $FAIL of $TOTAL checks failed, $SKIP skipped"
    exit 1
fi
if [ "$SKIP" -gt 0 ]; then
    echo "SECURITY REGRESSION INCOMPLETE: only $RAN of $TOTAL checks ran — $SKIP SKIPPED, so the security posture is NOT verified. This is NOT a pass."
    exit 2
fi
echo "SECURITY REGRESSION PASSED: all $TOTAL checks ran and passed"
exit 0
