"""Container-classification heuristics for :class:`DocumentationHTMLParser`.

These predicates decide, for a given tag + attributes, whether an element is page chrome
to skip, a (possibly non-semantic) content root to capture, or a breadcrumb trail. All
class/id matching is token-based so plural or compound class names don't trigger false
positives. Also derives a code block's language from ``class="language-xxx"`` style hints.
"""
from __future__ import annotations

from extraction.heuristics import (
    BOILERPLATE_HINTS,
    BOILERPLATE_TAGS,
    CONTENT_DIV_CLASS_HINTS,
)


class ClassificationMixin:
    """Boilerplate / content-root / breadcrumb / code-language heuristics."""

    def _is_boilerplate(self, tag: str, attrs: dict[str, str]) -> bool:
        """Whether an element's whole subtree is chrome and should be skipped.

        Breadcrumbs and supplemental content roots are explicitly rescued first, so a
        content container that merely contains a boilerplate-ish word isn't discarded.
        """
        if self._looks_like_breadcrumb(tag, attrs):
            return False
        if self._is_supplemental_content_root(tag, attrs):
            return False
        if tag in BOILERPLATE_TAGS:
            return True
        return self._marker_has_boilerplate_token(attrs)

    def _marker_has_boilerplate_token(self, attrs: dict[str, str]) -> bool:
        """True when any whole id/class token matches a boilerplate hint."""
        marker = f"{attrs.get('id', '')} {attrs.get('class', '')}".lower()
        tokens = set(marker.replace("-", " ").replace("_", " ").split())
        return bool(tokens & set(BOILERPLATE_HINTS))

    def _is_supplemental_content_root(self, tag: str, attrs: dict[str, str]) -> bool:
        """Recognize non-semantic content containers (e.g. ``<div class="markdown">``)."""
        marker = f"{attrs.get('id', '')} {attrs.get('class', '')}".lower()
        if tag == "nav" and "internal_nav" in marker:
            return True
        if tag in {"div", "section"}:
            tokens = set(marker.replace("-", " ").replace("_", " ").split())
            if tokens & CONTENT_DIV_CLASS_HINTS and not (tokens & set(BOILERPLATE_HINTS)):
                return True
        return False

    def _looks_like_breadcrumb(self, tag: str, attrs: dict[str, str]) -> bool:
        """True for nav/list/div containers labelled as a breadcrumb trail."""
        marker = f"{attrs.get('aria-label', '')} {attrs.get('class', '')} {attrs.get('id', '')}".lower()
        return tag in {"nav", "ol", "ul", "div"} and "breadcrumb" in marker

    def _looks_like_open_breadcrumb_end(self, tag: str) -> bool:
        """Tags that can close an open breadcrumb container."""
        return tag in {"nav", "ol", "ul", "div"}

    def _language_from_attrs(self, attrs: dict[str, str]) -> str | None:
        """Extract a code language from ``language-``/``lang-`` class or data tokens."""
        marker = f"{attrs.get('class', '')} {attrs.get('data-language', '')}".strip()
        for token in marker.replace(",", " ").split():
            if token.startswith("language-"):
                return token.removeprefix("language-")
            if token.startswith("lang-"):
                return token.removeprefix("lang-")
        return attrs.get("data-language") or None


__all__ = ["ClassificationMixin"]
