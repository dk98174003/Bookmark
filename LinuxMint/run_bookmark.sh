#!/usr/bin/env bash
set -euo pipefail

# Run the bookmark client from the terminal using the local ".venv"
# - If .venv is missing, it will run create_venv.sh first.
# - You can override which python file to run via: BOOKMARK_APP=yourfile.py ./run_bookmark.sh

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

VENV_PY=".venv/bin/python"
CREATE_SCRIPT="./create_venv.sh"

# Pick a default entrypoint if user didn't specify one
APP="${BOOKMARK_APP:-}"
if [[ -z "$APP" ]]; then
  if [[ -f "bookmark_improved.py" ]]; then
    APP="bookmark_improved.py"
  elif [[ -f "bookmark.py" ]]; then
    APP="bookmark.py"
  else
    echo "ERROR: Could not find bookmark_improved.py or bookmark.py in: $PROJECT_DIR"
    echo "Set BOOKMARK_APP to the filename you want to run, e.g.:"
    echo "  BOOKMARK_APP=main.py ./run_bookmark.sh"
    exit 3
  fi
fi

if [[ ! -x "$VENV_PY" ]]; then
  echo "No .venv found - creating it first..."
  if [[ ! -x "$CREATE_SCRIPT" ]]; then
    echo "ERROR: create_venv.sh not found or not executable: $CREATE_SCRIPT"
    exit 4
  fi
  bash "$CREATE_SCRIPT"
fi

echo "Project : $PROJECT_DIR"
echo "Python  : $VENV_PY"
echo "App     : $APP"
echo

exec "$VENV_PY" "$APP" "$@"

