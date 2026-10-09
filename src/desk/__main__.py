"""Entrypoint for python -m desk execution."""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
