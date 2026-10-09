#!/usr/bin/env python3
"""Convenience root entrypoint for Programming Desk CLI."""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to sys.path so 'desk' package can be imported directly
REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from desk.cli import main

if __name__ == "__main__":
    sys.exit(main())
