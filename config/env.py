"""Loading of the project's ``.env`` file.

A tiny, dependency-free ``.env`` reader (no ``python-dotenv`` requirement). It uses
``os.environ.setdefault`` so values already present in the real environment always win
over the file — the file only *fills gaps*. Moved verbatim from the old ``cli`` module
so the CLI's startup behavior is unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

#: The package root (directory containing this ``config`` package's parent).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(env_path: Path | None = None) -> bool:
    """Populate ``os.environ`` from a ``.env`` file; return whether one was found.

    Lines that are blank, comments (``#``), or lack ``=`` are skipped. Surrounding
    single/double quotes are stripped from values. Existing environment variables are
    never overwritten.
    """
    target_path = env_path or _PROJECT_ROOT / ".env"
    if not target_path.exists():
        return False

    for raw_line in target_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        cleaned_value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, cleaned_value)

    return True


__all__ = ["load_env_file"]
