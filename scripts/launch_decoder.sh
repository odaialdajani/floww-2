#!/usr/bin/env bash
# launch_decoder.sh
# One-shot launcher for the Confluence Decoder PWA on macOS.
# Starts: MongoDB → FastAPI backend (:8000) → React dev server (:3000) → PWA
#
# Usage:
#   ./scripts/launch_decoder.sh           # smart-start (reuses running services)
#   ./scripts/launch_decoder.sh --restart # force restart backend + react
#
# Add an alias so it's a one-keystroke launch:
#   echo 'alias decoder="bash $HOME/Documents/GitHub/floww/scripts/launch_decoder.sh"' >> ~/.zshrc
#   source ~/.zshrc
#   decoder      # done

set -e

REPO_ROOT="$HOME/Documents/GitHub/floww"
PWA_PATH="$HOME/Applications/Chrome Apps.localized/Meridian.app"
BACKEND_PORT=8000
REACT_PORT=3000
RESTART=${1:-}

if [[ ! -d "$REPO_ROOT" ]]; then
  echo "ERROR: repo not found at $REPO_ROOT"; exit 1
fi
if [[ ! -d "$PWA_PATH" ]]; then
  echo "ERROR: PWA not installed at $PWA_PATH"
  echo "Open Chrome, navigate to http://localhost:3000/, then File → Install Confluence Decoder"
  exit 1
fi

# ── Freshness check: warn (don't block) if local main is behind origin ──────
# Rationale: yesterday we burned ~30 min diagnosing "missing routes" that
# actually existed in newer commits the running backend hadn't loaded.
# This surfaces stale-code drift BEFORE you spend time on phantom bugs.
echo "[0/3] Freshness"
LOCAL_SHA=$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)
git -C "$REPO_ROOT" fetch origin main --quiet 2>/dev/null || true
REMOTE_SHA=$(git -C "$REPO_ROOT" rev-parse origin/main 2>/dev/null)
if [[ -z "$LOCAL_SHA" || -z "$REMOTE_SHA" ]]; then
  echo "  ⚠ git state unreadable — skipping freshness check"
elif [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
  echo "  on origin/main ✓  ($LOCAL_SHA)"
else
  BEHIND=$(git -C "$REPO_ROOT" rev-list --count "$LOCAL_SHA..origin/main" 2>/dev/null || echo "?")
  AHEAD=$(git -C "$REPO_ROOT" rev-list --count "origin/main..$LOCAL_SHA" 2>/dev/null || echo "?")
  echo "  ⚠ DRIFT — local: $LOCAL_SHA  origin: $REMOTE_SHA"
  echo "  ⚠ behind: $BEHIND commits   ahead: $AHEAD commits"
  if [[ "$BEHIND" != "0" && "$BEHIND" != "?" ]]; then
    echo "  ⚠ Commits you don't have yet (likely cause of any phantom bugs):"
    git -C "$REPO_ROOT" log --oneline "$LOCAL_SHA..origin/main" 2>/dev/null | head -10 | sed 's/^/      /'
    echo "  ⚠ Resolve with: cd $REPO_ROOT && git pull --rebase origin main"
  fi
  if [[ "$AHEAD" != "0" && "$AHEAD" != "?" ]]; then
    echo "  ⚠ Local-only commits (not yet pushed):"
    git -C "$REPO_ROOT" log --oneline "origin/main..$LOCAL_SHA" 2>/dev/null | head -10 | sed 's/^/      /'
  fi
fi

# ── Helper: is a port already listening? ────────────────────────────────────
port_listening() {
  lsof -i :"$1" -P -n 2>/dev/null | grep -q LISTEN
}

# ── Helper: kill whatever owns a port (used with --restart) ──────────────────
kill_port() {
  local pid
  pid=$(lsof -i :"$1" -P -n 2>/dev/null | grep LISTEN | awk '{print $2}' | head -1)
  if [[ -n "$pid" ]]; then
    echo "  killing PID $pid on port $1"
    kill "$pid" 2>/dev/null || true
    sleep 2
  fi
}

# ── 0. MongoDB ───────────────────────────────────────────────────────────────
echo "[0/4] MongoDB"
if pgrep -x mongod > /dev/null 2>&1; then
  echo "  already running ✓"
else
  echo "  starting mongod..."
  mongod --dbpath /opt/homebrew/var/mongodb --logpath /tmp/mongodb.log --fork 2>/dev/null || \
  mongod --dbpath ~/data/db --logpath /tmp/mongodb.log --fork 2>/dev/null || \
  echo "  WARN: could not start MongoDB (may need manual start)"
  sleep 2
fi

# ── 1. Backend (FastAPI on 8000) ─────────────────────────────────────────────
echo "[1/4] Backend (port $BACKEND_PORT)"
if [[ "$RESTART" == "--restart" ]] && port_listening $BACKEND_PORT; then
  kill_port $BACKEND_PORT
fi
if port_listening $BACKEND_PORT; then
  echo "  already running ✓"
else
  echo "  starting uvicorn..."
  cd "$REPO_ROOT/backend"
  source .venv/bin/activate
  # Unbuffered: otherwise all structlog app lines sit in the pipe buffer and
  # the log shows only uvicorn access lines, hiding startup/sweep evidence.
  PYTHONUNBUFFERED=1 nohup uvicorn server:app --port $BACKEND_PORT > /tmp/uvicorn_decoder.log 2>&1 &
  cd "$REPO_ROOT"
  # Wait up to 15s for it to bind
  for i in {1..15}; do
    sleep 1; port_listening $BACKEND_PORT && break
  done
  port_listening $BACKEND_PORT && echo "  started ✓" || { echo "  FAILED — see /tmp/uvicorn_decoder.log"; exit 1; }
fi

# ── 2. React (CRA dev server on 3000) ────────────────────────────────────────
echo "[2/4] React (port $REACT_PORT)"
if [[ "$RESTART" == "--restart" ]] && port_listening $REACT_PORT; then
  kill_port $REACT_PORT
fi
if port_listening $REACT_PORT; then
  echo "  already running ✓"
else
  echo "  starting npm start (this takes ~25s to compile)..."
  cd "$REPO_ROOT/frontend"
  nohup npm start > /tmp/react_decoder.log 2>&1 &
  cd "$REPO_ROOT"
  for i in {1..40}; do
    sleep 1; port_listening $REACT_PORT && break
  done
  port_listening $REACT_PORT && echo "  started ✓" || { echo "  FAILED — see /tmp/react_decoder.log"; exit 1; }
fi

# ── 3. Launch the PWA (NOT a Chrome tab) ─────────────────────────────────────
echo "[3/4] PWA"
# `open -a` launches the .app bundle — Chrome's PWA wrapper opens a borderless
# window pointed at the URL baked into the bundle (http://localhost:3000/).
# Using `open URL` here instead would route through the default URL handler
# and open a regular Chrome tab — exactly the behavior we DON'T want.
open -a "$PWA_PATH"
echo "  PWA launched ✓"

echo ""
echo "──── DECODER READY ────"
echo "Backend:  http://localhost:$BACKEND_PORT  (lsof PID: $(lsof -i :$BACKEND_PORT -P -n 2>/dev/null | grep LISTEN | awk '{print $2}' | head -1))"
echo "React:    http://localhost:$REACT_PORT   (lsof PID: $(lsof -i :$REACT_PORT -P -n 2>/dev/null | grep LISTEN | awk '{print $2}' | head -1))"
echo "PWA:      $PWA_PATH"
echo "Logs:     /tmp/uvicorn_decoder.log + /tmp/react_decoder.log"
echo "────────────────────────"
