"""CLI entry point for idlixdownloader"""

import sys
from .downloader import main

if __name__ == "__main__":
    sys.exit(main())
