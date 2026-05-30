"""Markdown extraction strategy for ``.md`` / ``.markdown`` resources.

Public entry point: :func:`extract_markdown`. The module name is preserved so the legacy
import ``from markdown_extraction import extract_markdown`` keeps working.
"""
from __future__ import annotations

from markdown_extraction.extractor import extract_markdown

__all__ = ["extract_markdown"]
