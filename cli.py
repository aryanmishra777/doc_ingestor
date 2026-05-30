"""Command-line entry point.

The CLI stays as a runnable top-level module for ``python cli.py`` while its implementation
is split into small ordered chunks under ``cli_app``.
"""
from __future__ import annotations

from pathlib import Path


def _load_cli_app() -> None:
    """Execute CLI chunks in this module namespace."""
    for source in sorted((Path(__file__).with_name("cli_app")).glob("[0-9][0-9]_*.py")):
        code = compile(source.read_text(encoding="utf-8"), str(source), "exec")
        exec(code, globals())


_load_cli_app()
