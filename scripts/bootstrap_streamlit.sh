#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/home/linuxbrew/.linuxbrew/bin/python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

rm -rf "$ROOT_DIR/.venv"
"$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
source "$ROOT_DIR/.venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$ROOT_DIR/requirements.txt"

echo
 echo "Listo. Ejecuta:"
echo "  $ROOT_DIR/.venv/bin/streamlit run $ROOT_DIR/streamlit_app.py"
