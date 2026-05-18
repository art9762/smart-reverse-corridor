"""Pytest config — make sure `app` is importable when running from the
`services/simulator/` directory in CI.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
