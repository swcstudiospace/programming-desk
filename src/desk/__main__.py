"""Entrypoint for python -m desk execution."""

import sys
from src.desk.cli import main

if __name__ == "__main__":
    sys.exit(main())
