"""Tunable thresholds for PDF analysis and extraction.

PDFs have no semantic structure, so extraction is driven entirely by typographic
heuristics: characters-per-page distinguishes scanned/sparse/prose documents, a font-size
ratio promotes large text to headings, and monospace font-name hints flag code. Gathering
the magic numbers here keeps them documented and tunable in one place.
"""
from __future__ import annotations

from typing import Literal

#: How a PDF's text density is classified, which selects an extraction strategy.
DensityLevel = Literal["light", "medium", "dense"]

#: Below this average chars/page a PDF is assumed to be scanned images (skip it).
SCANNED_CHARS_PER_PAGE = 50

#: At/above this chars/page (with few images) the PDF is treated as light prose.
LIGHT_CHARS_PER_PAGE = 800

#: At/above this chars/page (or enough tables) the PDF is treated as medium density.
MEDIUM_CHARS_PER_PAGE = 200

#: A text span larger than ``median * this`` is treated as a heading, not body text.
HEADING_SIZE_RATIO = 1.2

#: Substrings in a span's font name that indicate monospaced (code) text.
MONO_FONT_HINTS = (
    "courier", "consolas", "monaco", "mono", "code", "inconsolata", "jetbrains",
)

__all__ = [
    "DensityLevel",
    "SCANNED_CHARS_PER_PAGE",
    "LIGHT_CHARS_PER_PAGE",
    "MEDIUM_CHARS_PER_PAGE",
    "HEADING_SIZE_RATIO",
    "MONO_FONT_HINTS",
]
