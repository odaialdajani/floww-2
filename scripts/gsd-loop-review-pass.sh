#!/bin/zsh
# gsd-loop REVIEW lane — one playbook pass per wake.
# Scheduled task: "gsd-loop review — mrbeast1179-sketch/floww"
# (launchd com.nav.gsd-loop.review.floww, StartInterval 900).
# State (.gsd/scheduled_tasks.review.lock), log, lockdir and plist are all
# separate from the build lane so the two lanes never mix state.
# The reviewer never touches git: read-only + gh verdict comments.
# Test plumbing without running a pass: GSD_DRY_RUN=1 GSD_STATE_FILE=/tmp/x.json
set -u

REPO=/Users/nav/Documents/GitHub/floww
PLAYBOOK=/Users/nav/.agents/skills/gsd-loop-review/playbook.md
STATE_FILE="${GSD_STATE_FILE:-$REPO/.gsd/scheduled_tasks.review.lock}"
LOG=/tmp/gsd-loop-review.log
LOCKDIR=/tmp/gsd-loop-review.lock
OPENCODE=/Users/nav/.opencode/bin/opencode
NPX=/Users/nav/.nvm/versions/node/v24.14.1/bin/npx
PY=/usr/bin/python3
export PATH="/Users/nav/.nvm/versions/node/v24.14.1/bin:/opt/homebrew/bin:/Users/nav/.opencode/bin:/usr/bin:/bin:/usr/sbin:/sbin"

log() { echo "[$(date -u +%FT%TZ)] $*" >> "$LOG"; }

gh_auth_ok() {
  gh auth status >/dev/null 2>&1 && return 0
  # keychain unavailable under launchd? fall back to the user-owned token file
  [ -f "$HOME/.gh_token_env" ] && { set -a; . "$HOME/.gh_token_env" 2>/dev/null; set +a; }
  gh auth status >/dev/null 2>&1
}

mkdir "$LOCKDIR" 2>/dev/null || { log "skip: previous pass still running"; exit 0; }
trap 'rmdir "$LOCKDIR" 2>/dev/null || true' EXIT

st() { local v; v="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], sys.argv[3]))' "$STATE_FILE" "$1" "$2" 2>/dev/null)"; [ -z "$v" ] && v="$2"; print -r -- "$v"; }
idle="$(st idle_count 0)"; paused="$(st paused False)"; last="$(st last_run 0)"
now="$(date +%s)"
interval=900; [ "$idle" = "0" ] || interval=3600

if [ "$paused" = "True" ]; then
  log "paused (see $STATE_FILE). Resume: set paused=false after clearing the stop condition."
  exit 0
fi
if [ "$(( now - last ))" -lt "$interval" ]; then exit 0; fi  # backing off

# --- preflight (missing = blocked per playbook) ---
EVENT=""; REASON=""
if ! head -c 1 "$REPO/CLAUDE.md" >/dev/null 2>&1; then EVENT=blocked; REASON="tcc-documents";
elif [ ! -x "$OPENCODE" ]; then EVENT=blocked; REASON="opencode-missing";
elif ! command -v gh >/dev/null 2>&1; then EVENT=blocked; REASON="gh-missing";
elif ! gh_auth_ok; then EVENT=blocked; REASON="gh-auth";
elif [ ! -f "$PLAYBOOK" ]; then EVENT=blocked; REASON="playbook-missing"; fi

if [ -z "$EVENT" ]; then
  PASSLOG="/tmp/gsd-loop-review-pass-${now}.log"
  PROMPT="Run exactly ONE gsd-loop REVIEW pass for repo $REPO (owner/repo mrbeast1179-sketch/floww). Read and follow ONLY this playbook: $PLAYBOOK. Rules: audit-only — never touch git (no checkout, commit, push, worktree changes), never merge; verdicts go in as issue/PR comments per the playbook. Your final response MUST end with exactly one line of the form GSD_LOOP_RESULT={\"lane\":\"review\",\"status\":\"work|idle|blocked\",\"reason\":\"short-reason\"} and no text after it."
  if [ "${GSD_DRY_RUN:-0}" = "1" ]; then
    echo 'GSD_LOOP_RESULT={"lane":"review","status":"idle","reason":"dry-run"}' > "$PASSLOG"
  else
    # Reviewer is read-only: file writes, interactive questions and every
    # git-mutating command denied (--auto approves the rest).
    export OPENCODE_PERMISSION='{"question":"deny","edit":"deny","bash":{"*":"allow","*commit*":"deny","*push*":"deny","*worktree*":"deny","*checkout*":"deny","*--force*":"deny","*reset --hard*":"deny","*rebase*":"deny","*clean -fd*":"deny"}}'
    "$OPENCODE" run --auto --dir "$REPO" "$PROMPT" > "$PASSLOG" 2>&1 &
    pid=$!; waited=0
    while kill -0 "$pid" 2>/dev/null; do
      [ "$waited" -ge 2700 ] && { kill -TERM "$pid" 2>/dev/null; sleep 15; kill -KILL "$pid" 2>/dev/null; REASON="pass-timeout"; break; }
      sleep 30; waited=$(( waited + 30 ))
    done
    wait "$pid" 2>/dev/null
  fi
  RESULT="$(grep -o 'GSD_LOOP_RESULT={[^}]*}' "$PASSLOG" 2>/dev/null | tail -1)"
  STATUS="$(echo "$RESULT" | grep -o '"status":"[a-z]*"' | cut -d'"' -f4)"
  case "$STATUS" in
    work) EVENT=work ;;
    idle) EVENT=idle ;;
    *)    EVENT=blocked; [ -z "$REASON" ] && REASON="no-result-line" ;;
  esac
  [ "$EVENT" = "blocked" ] && log "blocked pass ($REASON), see $PASSLOG"
  if [ "$REASON" = "tcc-documents" ]; then
    log "REMEDIATION: launchd cannot read $REPO (macOS TCC: ~/Documents). Grant Full Disk Access to /bin/zsh (System Settings > Privacy & Security), then set paused=false in $STATE_FILE. Until then, run passes manually from Terminal: ./scripts/gsd-loop-review-pass.sh"
  fi
fi

POLICY="$("$NPX" -y @opengsd/gsd-loop@latest policy "$EVENT" "$idle" 2>/dev/null | tail -1)"
ACTION="$(echo "$POLICY" | tr ' ' '\n' | grep '^action=' | cut -d= -f2)"
NEWIDLE="$(echo "$POLICY" | tr ' ' '\n' | grep '^idle_count=' | cut -d= -f2)"
NEWINT="$(echo "$POLICY" | tr ' ' '\n' | grep '^interval_minutes=' | cut -d= -f2)"
[ -z "$ACTION" ] && { ACTION=pause; NEWIDLE="$idle"; NEWINT=0; }
PAUSED=False; [ "$ACTION" = "pause" ] && PAUSED=True
"$PY" - "$STATE_FILE" "$NEWIDLE" "$now" "$PAUSED" "$NEWINT" <<'EOF' 2>/dev/null || log "WARN: state write failed"
import json,sys
p,i,ts,pa,n = sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5]
try: d=json.load(open(p))
except Exception: d={}
d.update({"lane":"review","repo":"mrbeast1179-sketch/floww","task":"gsd-loop review \u2014 mrbeast1179-sketch/floww","idle_count":int(i),"last_run":int(ts),"paused":(pa=="True"),"interval_minutes":int(n)})
json.dump(d,open(p,"w"),indent=2)
EOF
log "pass done event=$EVENT action=$ACTION idle=$NEWIDLE next_in=${NEWINT}m"
[ "$ACTION" = "pause" ] && log "LOOP PAUSED (3x idle or blocked). Human: clear the condition, set paused=false in $STATE_FILE."
exit 0
