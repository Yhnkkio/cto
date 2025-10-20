# Enable running `python -m cto` without installing the package by adding `src/` to sys.path
# This file is discovered automatically by the Python interpreter if it is on sys.path.
from __future__ import annotations

import os
import sys

_here = os.path.dirname(__file__)
src = os.path.join(_here, "src")
if os.path.isdir(src) and src not in sys.path:
    sys.path.insert(0, src)
