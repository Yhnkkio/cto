# Ensure src/ is on sys.path for local development so `python -m adb_overlay_server` works
import os
import sys

_here = os.path.dirname(__file__)
_src = os.path.join(_here, "src")
if os.path.isdir(_src) and _src not in sys.path:
    sys.path.insert(0, _src)
