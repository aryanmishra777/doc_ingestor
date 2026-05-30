"""PDF extraction strategy.

Public entry point: :func:`extract_pdf`. Internals are split by concern — density
analysis, per-page block building, the three segmentation strategies, and record
assembly. The module name is preserved for the legacy import
``from pdf_extraction import extract_pdf``.
"""
from __future__ import annotations

from pdf_extraction.extractor import extract_pdf

__all__ = ["extract_pdf"]
