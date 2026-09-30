"""Entry point for the packaged .exe (PyInstaller)."""
import sys

from uti260b.gui import main

if __name__ == "__main__":
    sys.exit(main())
