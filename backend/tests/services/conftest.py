"""Shared conftest for service-level tests.

Adds backend/ to sys.path so that ``from services.X import Y`` works
without each test file having its own sys.path.insert hack.
"""

import sys
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent.parent  # backend/
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
