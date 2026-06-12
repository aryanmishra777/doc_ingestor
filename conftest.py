"""Pytest bootstrap.

Guarantees the project root (this directory) is importable as the top of the flat
package namespace, so ``import adaptive`` / ``from net import http_get`` resolve whether
pytest is invoked from the repo root or elsewhere. The standalone ``test_*.py`` scripts
also insert this path themselves; doing it here too makes ``pytest`` collection robust.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Tests must never read or write the user's cross-run playbook memory.
os.environ.setdefault("DOC_INGESTOR_PLAYBOOK", "0")
