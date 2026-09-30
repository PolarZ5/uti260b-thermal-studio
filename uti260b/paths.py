"""Where the app finds its resources and writes its files (source checkout or packaged .exe)."""
import os
from pathlib import Path
import sys

FROZEN = getattr(sys, "frozen", False)

# bundled read-only resources (samples for the demo mode)
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
SAMPLES = RESOURCES / "samples"

if FROZEN:
    _appdata = Path(os.environ.get("APPDATA", Path.home())) / "UTi260B Thermal Studio"
    SETTINGS = _appdata / "settings.json"
    DEFAULT_CAPTURES = Path.home() / "Documents" / "UTi260B Captures"
else:
    _root = Path(__file__).resolve().parents[1]
    SETTINGS = _root / "settings.json"
    DEFAULT_CAPTURES = _root / "captures"
