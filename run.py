#!/usr/bin/env python3
"""Mushroom Pet entry point."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# crisp per-monitor DPI handling, set before Qt is imported
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

from mushroompet.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
