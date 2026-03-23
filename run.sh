#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="python3"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
fi
export PYTHONPATH="$ROOT/.deps${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" "$ROOT/main.py" "$@"
