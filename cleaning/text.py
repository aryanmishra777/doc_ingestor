"""Low-level string normalization used by the cleaning layer.

These helpers operate on raw extracted text and make it safe and uniform for Markdown
output: NFC Unicode normalization, removal of zero-width and control characters, CRLF →
LF, and whitespace collapsing. Prose and code are treated differently — code must keep
its tabs and internal newlines, whereas prose collapses runs of spaces and blank lines.
"""
from __future__ import annotations

import re
import unicodedata

#: Invisible characters that survive copy/paste from docs and corrupt diffs/Markdown.
#: Written as escapes on purpose so the source stays readable and reviewable.
ZERO_WIDTH_CHARS = {
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "﻿",  # BOM / zero-width no-break space
}

#: Collapses 3+ consecutive newlines down to a single blank line.
MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")

#: Collapses runs of spaces/tabs to a single space (prose only).
SPACES_TABS_RE = re.compile(r"[ \t]+")


def clean_prose(value: str) -> str:
    """Normalize a run of prose: Unicode, control chars, whitespace, then ``strip``."""
    text = normalize_unicode(value)
    text = strip_control_chars(text, keep_newline=True, keep_tab=False)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = SPACES_TABS_RE.sub(" ", text)
    text = MULTI_BLANK_LINE_RE.sub("\n\n", text)
    return text.strip()


def clean_code(value: str) -> str:
    """Normalize a code block, preserving tabs and internal newlines verbatim."""
    text = normalize_unicode(value)
    text = strip_control_chars(text, keep_newline=True, keep_tab=True)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_unicode(value: str) -> str:
    """Apply NFC normalization so visually-identical strings compare/hash equal."""
    return unicodedata.normalize("NFC", value)


def strip_control_chars(value: str, keep_newline: bool, keep_tab: bool) -> str:
    """Drop zero-width and Unicode "Other" (category ``C*``) control characters.

    Newlines and tabs are retained selectively via the flags so the same routine serves
    both prose (newlines only) and code (newlines and tabs).
    """
    chars: list[str] = []
    for char in value:
        if char in ZERO_WIDTH_CHARS:
            continue
        if char == "\n" and keep_newline:
            chars.append(char)
            continue
        if char == "\t" and keep_tab:
            chars.append(char)
            continue
        category = unicodedata.category(char)
        if category.startswith("C"):
            continue
        chars.append(char)
    return "".join(chars)


__all__ = [
    "ZERO_WIDTH_CHARS",
    "MULTI_BLANK_LINE_RE",
    "SPACES_TABS_RE",
    "clean_prose",
    "clean_code",
    "normalize_unicode",
    "strip_control_chars",
]
