"""Tag/class heuristics that drive the structure-aware HTML parser.

Documentation pages rarely use clean semantic HTML, so the parser leans on two lists:
an **allowlist** of containers that mark real content (``CONTENT_ROOT_TAGS`` plus
content-y class tokens) and a **denylist** of chrome to skip (``BOILERPLATE_TAGS`` and
``BOILERPLATE_HINTS``). Matching is done on *whole tokens* (``"main-content"`` →
``{"main", "content"}``) so a wrapper class like ``"layout__2-sidebars"`` doesn't get
discarded just because it contains the substring "sidebar".

``VOID_TAGS`` is critical for correctness: HTML void elements (and unclosed SVG leaf
elements inside nav icons) never receive an end tag, so they must not increment the
skip/nesting depth — otherwise one stray ``<path>`` permanently corrupts parsing.
"""
from __future__ import annotations

#: Elements whose entire subtree is page chrome, not content.
BOILERPLATE_TAGS = {"nav", "footer", "aside", "header", "script", "style", "noscript"}

#: Semantic elements that unambiguously wrap the main content.
CONTENT_ROOT_TAGS = {"main", "article"}

#: Class/id tokens that mark a container as chrome to skip.
BOILERPLATE_HINTS = ("cookie", "consent", "sidebar", "menu", "navbar", "footer")

#: Class/id tokens that suggest a ``div``/``section`` is the primary content container.
CONTENT_DIV_CLASS_HINTS = frozenset({
    "content", "main", "docs", "documentation", "markdown",
    "prose", "readme", "body", "entry", "post",
})

#: Below this many characters of prose, a parse result is treated as "sparse" and a
#: richer extraction strategy (full-page parse, then trafilatura) is attempted.
SPARSE_CONTENT_CHAR_THRESHOLD = 120

#: Void/leaf elements that never get a closing tag. SVG leaves are included because nav
#: icons frequently embed unclosed ``<path>``/``<use>`` etc., which would otherwise break
#: depth tracking.
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
    "path", "circle", "ellipse", "line", "polyline", "polygon",
    "rect", "stop", "use",
}

__all__ = [
    "BOILERPLATE_TAGS",
    "CONTENT_ROOT_TAGS",
    "BOILERPLATE_HINTS",
    "CONTENT_DIV_CLASS_HINTS",
    "SPARSE_CONTENT_CHAR_THRESHOLD",
    "VOID_TAGS",
]
