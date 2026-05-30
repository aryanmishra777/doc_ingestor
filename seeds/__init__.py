"""Seed discovery facade.

The seed-discovery implementation is split into small ordered chunks that execute in
this package namespace. That keeps ``import seeds`` and monkeypatching behavior identical
to the former single-file module while removing the oversized source file.
"""
from __future__ import annotations

from pathlib import Path


def _load_parts() -> None:
    """Execute seed-discovery chunks in source order."""
    for source in sorted(Path(__file__).parent.glob("[0-9][0-9]_*.py")):
        code = compile(source.read_text(encoding="utf-8"), str(source), "exec")
        exec(code, globals())


_load_parts()
