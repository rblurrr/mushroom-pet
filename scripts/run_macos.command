#!/bin/bash
# Double-click this in Finder to start the pet.
cd "$(dirname "$0")/.."

PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  echo "Python 3 not found. Install it from https://www.python.org/downloads/macos/"
  read -r -p "Press return to close."
  exit 1
fi

if ! "$PY" -c "import PySide6" >/dev/null 2>&1; then
  echo "Installing PySide6 (one time, ~100 MB)..."
  "$PY" -m pip install --user -r requirements.txt || {
    echo "Install failed."; read -r -p "Press return to close."; exit 1; }
fi

# Optional: lets him walk on and climb your open windows.
if ! "$PY" -c "import Quartz" >/dev/null 2>&1; then
  echo "Installing optional window support (pyobjc)..."
  "$PY" -m pip install --user pyobjc-framework-Quartz pyobjc-framework-Cocoa || \
    echo "Skipped - he'll still walk the bottom of the screen."
fi

nohup "$PY" run.py >/dev/null 2>&1 &
echo "Mushroom Pet started."
