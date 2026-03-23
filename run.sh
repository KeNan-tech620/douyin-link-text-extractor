#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT/.deps${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$ROOT/main.py" "$@"
