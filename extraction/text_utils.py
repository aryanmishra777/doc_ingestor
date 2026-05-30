"""Small text helpers shared by the HTML parser and the trafilatura fallback."""
from __future__ import annotations

#: Substrings that strongly imply a text run is source code rather than prose. Used by
#: the trafilatura fallback to decide whether an ambiguous ``<quote>`` is a code block.
CODE_TOKEN_PATTERNS = (
    "{", "}", "();", ");", "=>", "==", "!=", "->",
    "function ", "const ", "let ", "var ", "return ",
    "import ", "from ", "def ", "class ", "public ",
    "#include", "<?php",
)


def squash_text(text: str) -> str:
    """Collapse all runs of whitespace to single spaces and trim."""
    return " ".join(text.split())


def escape_markdown_link_text(text: str) -> str:
    """Escape ``[``/``]`` so link labels can't break Markdown link syntax."""
    return text.replace("[", "\\[").replace("]", "\\]")


def looks_like_code(text: str) -> bool:
    """Heuristic: does this text read like source code?

    Multi-line text containing a code token, or a tight single line with several
    ``;``/braces, is treated as code. Deliberately conservative to avoid misclassifying
    ordinary prose.
    """
    if "\n" in text and any(token in text for token in CODE_TOKEN_PATTERNS):
        return True
    return text.count(";") >= 2 or text.count("{") >= 1 and text.count("}") >= 1


__all__ = ["CODE_TOKEN_PATTERNS", "squash_text", "escape_markdown_link_text", "looks_like_code"]
