"""Adaptive crawler facade.

The adaptive state machine is split into small ordered chunks that execute in this
package namespace. Public and test-touched private names remain available exactly where
legacy callers expect them.
"""
from __future__ import annotations

from pathlib import Path


def _load_parts() -> None:
    """Execute adaptive crawler chunks in source order."""
    for source in sorted(Path(__file__).parent.glob("[0-9][0-9]_*.py")):
        code = compile(source.read_text(encoding="utf-8"), str(source), "exec")
        exec(code, globals())


_load_parts()
