"""Entrypoint for ``python -m garmin_health``."""

import sys

from garmin_health.cli import main

if __name__ == "__main__":
    sys.exit(main())
