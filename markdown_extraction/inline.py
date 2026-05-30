"""Inline-token flattening for the Markdown extractor.

Converts a markdown-it ``inline`` token's children into a single plain-ish string while
preserving inline code (backticks) and image alt text, and harvesting link hrefs into the
shared ``links`` list for crawling. Emphasis wrappers are unwrapped (their nested text is
kept). :func:`strip_html` reduces embedded raw-HTML blocks to text.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def flatten_inline(inline_token, links: list[str], base_url: str) -> str:
    """Flatten an inline token to text, collecting link hrefs as a side effect."""
    parts: list[str] = []
    for child in inline_token.children or []:
        t = child.type
        if t == "text":
            parts.append(child.content)
        elif t == "code_inline":
            parts.append(f"`{child.content}`")
        elif t == "softbreak":
            parts.append(" ")
        elif t == "hardbreak":
            parts.append("\n")
        elif t == "link_open":
            href = next((v for k, v in (child.attrs or {}).items() if k == "href"), None)
            if href:
                links.append(urljoin(base_url, href))
        elif t == "image":
            alt = child.content or ""
            if alt:
                parts.append(alt)
        # em/strong/link_close/etc.: ignore the wrapper, keep nested text.
    return " ".join("".join(parts).split())


def strip_html(text: str) -> str:
    """Replace HTML tags with spaces so a raw-HTML block degrades to readable text."""
    return _HTML_TAG_RE.sub(" ", text)


__all__ = ["flatten_inline", "strip_html"]
