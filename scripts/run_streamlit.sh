#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STREAMLIT_BIN="$ROOT_DIR/.venv/bin/streamlit"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

needs_bootstrap=0
if [[ ! -x "$STREAMLIT_BIN" || ! -x "$PYTHON_BIN" ]]; then
  needs_bootstrap=1
elif ! "$PYTHON_BIN" - <<'PY'
import importlib.util
raise SystemExit(0 if importlib.util.find_spec('streamlit') and importlib.util.find_spec('sklearn') else 1)
PY
then
  needs_bootstrap=1
fi

if [[ "$needs_bootstrap" -eq 1 ]]; then
  echo "No encuentro $STREAMLIT_BIN. Creando entorno..."
  "$ROOT_DIR/scripts/bootstrap_streamlit.sh"
fi

exec "$STREAMLIT_BIN" run "$ROOT_DIR/streamlit_app.py" "$@"
