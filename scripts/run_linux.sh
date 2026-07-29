#!/bin/bash
# Untested, but the generic backend runs: walking, dragging, bubbles, menus, reminders.
cd "$(dirname "$0")/.."
PY=$(command -v python3 || command -v python)
"$PY" -c "import PySide6" >/dev/null 2>&1 || "$PY" -m pip install --user -r requirements.txt
exec "$PY" run.py
