"""PyInstaller entry script: run the app exactly like `python -m ginga`."""

import sys

from ginga.__main__ import main

sys.exit(main())
