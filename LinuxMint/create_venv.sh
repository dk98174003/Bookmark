#!/usr/bin/env bash
set -euo pipefail

# Create/refresh a local virtualenv in ".venv" (project folder = script folder)
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

echo "Project  : $PROJECT_DIR"
echo "Python   : $PYTHON_BIN"
echo "Venv dir : $VENV_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: '$PYTHON_BIN' not found. Install Python 3 first."
  exit 1
fi

# Create venv (if it fails on Debian/Ubuntu, you likely miss python3-venv)
if [[ ! -d "$VENV_DIR" ]]; then
  echo "[1/3] Creating venv..."
  if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    echo
    echo "Venv creation failed."
    echo "On Debian/Ubuntu/Mint, install the venv package and retry:"
    echo "  sudo apt update && sudo apt install -y python3-venv python3-pip"
    exit 2
  fi
else
  echo "[1/3] Venv already exists (skipping create)."
fi

echo "[2/3] Upgrading pip tooling..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel

if [[ -f "requirements.txt" ]]; then
  echo "[3/3] Installing requirements.txt..."
  "$VENV_DIR/bin/python" -m pip install -r requirements.txt
else
  echo "[3/3] No requirements.txt found (skipping)."
  echo "Tip: create one later with:"
  echo "  $VENV_DIR/bin/python -m pip freeze > requirements.txt"
fi

echo
echo "Done."
echo "Activate with:"
echo "  source $VENV_DIR/bin/activate"
