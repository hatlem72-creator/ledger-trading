#!/usr/bin/env bash
# Build (and optionally push) the password-protected Market Ledger site.
# Usage:
#   ./build.sh              # render + encrypt index.html
#   ./build.sh --update     # fetch closing prices first, then build
#   ./build.sh --push       # build, then commit index.html and push
#   ./build.sh --update --push
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

STORE_DEFAULT="/cursor/stores/store-a2949f1e-d5b4-40ef-9663-3d29b9ebfd5b/papertrading/state.json"
STATE_LOCAL="$ROOT/state.json"
PW="$ROOT/pw.txt"
PLAIN="$ROOT/plaintext.html"
OUT="$ROOT/index.html"

DO_UPDATE=0
DO_PUSH=0
for arg in "$@"; do
  case "$arg" in
    --update) DO_UPDATE=1 ;;
    --push) DO_PUSH=1 ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$PW" ]]; then
  echo "Missing $PW — create it with the site password (never commit this file)." >&2
  exit 1
fi

# Prefer the persistent session store, fall back to the local (gitignored) copy.
if [[ -f "${STATE_PATH:-}" ]]; then
  STATE="${STATE_PATH}"
elif [[ -f "$STORE_DEFAULT" ]]; then
  STATE="$STORE_DEFAULT"
  cp "$STORE_DEFAULT" "$STATE_LOCAL"
elif [[ -f "$STATE_LOCAL" ]]; then
  STATE="$STATE_LOCAL"
else
  echo "No state.json found. Set STATE_PATH or place state.json next to build.sh." >&2
  exit 1
fi

echo "Using state: $STATE"

if [[ "$DO_UPDATE" -eq 1 ]]; then
  python3 "$ROOT/update_prices.py" "$STATE"
  # keep local and store copies in sync when possible
  if [[ "$STATE" != "$STATE_LOCAL" ]]; then
    cp "$STATE" "$STATE_LOCAL"
  fi
  if [[ "$STATE" != "$STORE_DEFAULT" && -d "$(dirname "$STORE_DEFAULT")" ]]; then
    cp "$STATE" "$STORE_DEFAULT" || true
  fi
else
  if [[ "$STATE" != "$STATE_LOCAL" ]]; then
    cp "$STATE" "$STATE_LOCAL"
  fi
fi

# Ensure history exists (opening point) and write it back.
python3 - << PY
from pathlib import Path
import json, sys
sys.path.insert(0, "$ROOT")
from render import ensure_history, load_state
p = Path("$STATE")
state = ensure_history(load_state(p))
p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
Path("$STATE_LOCAL").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
store = Path("$STORE_DEFAULT")
if store.parent.exists() and p.resolve() != store.resolve():
    try:
        store.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
print("history points:", len(state.get("history") or []))
PY

python3 "$ROOT/render.py" "$STATE" "$PLAIN"
python3 "$ROOT/encrypt.py" "$PLAIN" "$PW" "$OUT"
rm -f "$PLAIN"
python3 "$ROOT/verify_decrypt.py" "$OUT" "$PW"

if [[ "$DO_PUSH" -eq 1 ]]; then
  if [[ ! -d "$ROOT/.git" ]]; then
    echo "No git repository here; skip push." >&2
    exit 1
  fi
  git add -- index.html fonts/UnifrakturMaguntia.woff .nojekyll README.md build.sh render.py encrypt.py update_prices.py verify_decrypt.py .gitignore fonts/README.md 2>/dev/null || true
  # never add pw.txt or state.json
  if git ls-files --error-unmatch pw.txt >/dev/null 2>&1; then
    echo "REFUSING TO PUSH: pw.txt is tracked" >&2
    exit 1
  fi
  if git ls-files --error-unmatch state.json >/dev/null 2>&1; then
    echo "REFUSING TO PUSH: state.json is tracked" >&2
    exit 1
  fi
  if git diff --cached --quiet; then
    echo "Nothing new to commit."
  else
    git -c user.name=hatlem72-creator -c user.email=hatlem72-creator@users.noreply.github.com \
      commit -m "Update encrypted Market Ledger"
  fi
  git push
fi

echo "Build done: $OUT"
