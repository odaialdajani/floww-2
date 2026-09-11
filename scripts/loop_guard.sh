#!/usr/bin/env bash
# scripts/loop_guard.sh — own-paths staging + staged-ownership gate.
#
# Why: a prior incident swept one agent's staged hunks into another agent's
# commit. Rule: stage ONLY your owned paths (per institutional_loop/
# OWNERSHIP.md), never `git add -A` / `commit -a`.
#
# Usage:
#   scripts/loop_guard.sh stage <A|B|C|D>      # git-add only owned worktree paths
#   scripts/loop_guard.sh check-staged <AGENT> # exit 1 on foreign-owned staged files
#   (pre-commit hook body): LOOP_AGENT=A scripts/loop_guard.sh hook
#
# SHARED files need a LEDGER sign-off: pass LOOP_SIGNOFF=<ledger-line-ref>
# (e.g. LOOP_SIGNOFF="2026-09-05 C: flow_alerts C-REGION ok"). Without it,
# SHARED staged files fail the check. UNOWNED paths pass with a warning.
# LOOP_AGENT unset (humans/Nav) -> hook passes silently.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
MAP="$REPO_ROOT/institutional_loop/OWNERSHIP.md"
cd "$REPO_ROOT"

owner_of() {
  local path="$1" glob owner _empty
  while IFS='|' read -r _empty _glob _owner _note; do
    glob="$(echo "$_glob" | xargs)"; owner="$(echo "$_owner" | xargs)"
    [[ "$glob" == Path* || "$glob" == "---"* || -z "$glob" ]] && continue
    # shellcheck disable=SC2053
    if [[ "$path" == $glob ]]; then
      echo "$owner"
      return 0
    fi
  done < <(grep -E '^\|' "$MAP")
  echo "UNOWNED"
}

cmd="${1:-}"; agent="${2:-}"
case "$cmd" in
  hook)
    [[ -z "${LOOP_AGENT:-}" ]] && exit 0
    agent="$LOOP_AGENT"
    ;&
  check-staged)
    [[ -z "$agent" ]] && { echo "usage: loop_guard.sh check-staged <A|B|C|D>"; exit 2; }
    fail=0
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      own="$(owner_of "$f")"
      if [[ "$own" == "$agent" || "$own" == "UNOWNED" ]]; then
        [[ "$own" == "UNOWNED" ]] && echo "warn: UNOWNED staged file (D reviews at sync): $f"
      elif [[ "$own" == "SHARED" ]]; then
        if [[ -n "${LOOP_SIGNOFF:-}" ]]; then
          echo "ok (shared, sign-off $LOOP_SIGNOFF): $f"
        else
          echo "BLOCKED shared file without LOOP_SIGNOFF: $f (owner: cross-region — log sign-off in LEDGER)"
          fail=1
        fi
      else
        echo "BLOCKED foreign-owned file: $f (owner: $own, you: $agent)"
        fail=1
      fi
    done < <(git diff --cached --name-only)
    if [[ "$fail" -ne 0 ]]; then
      echo "loop-guard: unstage foreign files or set LOOP_SIGNOFF; never commit -a"
      exit 1
    fi
    echo "loop-guard: staged set clean for $agent"
    ;;
  stage)
    [[ -z "$agent" ]] && { echo "usage: loop_guard.sh stage <A|B|C|D>"; exit 2; }
    staged=0; skipped=0
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      own="$(owner_of "$f")"
      if [[ "$own" == "$agent" ]]; then
        git add -- "$f" && staged=$((staged + 1))
      else
        echo "skip ($own): $f"
        skipped=$((skipped + 1))
      fi
    done < <(git status --porcelain -uall | awk '{print $2}')
    echo "loop-guard: staged $staged owned file(s), skipped $skipped (foreign/shared/unowned)"
    ;;
  *)
    echo "usage: loop_guard.sh {stage|check-staged|hook} <A|B|C|D>"
    exit 2
    ;;
esac
