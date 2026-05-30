"""The breadth-first crawl frontier.

:class:`LinkTraversalFrontier` is the crawl's queue and gatekeeper. It hands out URLs in
BFS order (respecting optional page/depth caps), records what it has already seen so a
page is never visited twice, and decides whether a newly discovered link is *relevant* —
same domain, not an asset, not an excluded section, and within the documentation subtree.

The relevance rule deliberately restricts the crawl to the start URL's subtree to prevent
"URL explosion": if the start path already sits inside a docs tree (e.g.
``/docs/Web/JavaScript``), it won't escape into sibling subtrees; the broader
doc-signal fallback only applies when starting *above* the docs tree.
"""
from __future__ import annotations

from collections import deque
from urllib.parse import urlparse

from traversal.url_rules import (
    ASSET_EXTENSIONS,
    DOC_PATH_SIGNALS,
    EXCLUDED_PATH_SIGNALS,
    normalize_url,
)


class LinkTraversalFrontier:
    """A bounded, de-duplicating BFS queue scoped to one documentation site."""

    def __init__(self, start_url: str, max_pages: int | None = None, max_depth: int | None = None):
        self.start_url = normalize_url(start_url, None)
        parsed_start = urlparse(self.start_url)
        self.allowed_domain = parsed_start.netloc
        # Lower-cased to match the lower-cased path used in relevance comparisons.
        self.start_path = (parsed_start.path.rstrip("/") or "/").lower()
        self.queue: deque[tuple[str, int]] = deque([(self.start_url, 0)])
        self.seen = {self.start_url}
        self.pages_yielded = 0
        self.max_pages = max_pages
        self.max_depth = max_depth

    def get_next_url(self) -> tuple[str | None, int]:
        """Pop the next ``(url, depth)``, or ``(None, -1)`` when done/at the page cap."""
        if not self.queue:
            return None, -1
        if self.max_pages is not None and self.pages_yielded >= self.max_pages:
            return None, -1
        next_url, depth = self.queue.popleft()
        self.pages_yielded += 1
        return next_url, depth

    def register_discovered_links(self, source_url: str, new_links: list[str], current_depth: int) -> None:
        """Enqueue newly found links that are unseen and relevant (subject to depth cap)."""
        if self.max_depth is not None and current_depth >= self.max_depth:
            return
        for raw_link in new_links:
            normalized_link = normalize_url(raw_link, source_url)
            if not normalized_link or normalized_link in self.seen:
                continue
            if not self._is_relevant_edge(normalized_link):
                continue
            self.seen.add(normalized_link)
            self.queue.append((normalized_link, current_depth + 1))

    def _is_relevant_edge(self, url: str) -> bool:
        """Whether ``url`` belongs to this crawl (domain, asset, scope, doc-signal rules)."""
        parsed = urlparse(url)
        if parsed.netloc.lower() != self.allowed_domain:
            return False
        if parsed.scheme.lower() not in {"http", "https"}:
            return False

        path = parsed.path.lower()
        if path.endswith(ASSET_EXTENSIONS):
            return False
        if any(signal in path for signal in EXCLUDED_PATH_SIGNALS):
            return False
        if "/changelog" in path and "/changelog" not in self.start_path.lower():
            return False
        if path in {"", "/"} or path.startswith(self.start_path.rstrip("/") + "/"):
            return True
        # Doc-signal fallback only when the start URL is *above* the docs tree; otherwise
        # it would let the crawler escape into sibling subtrees (URL explosion).
        if any(signal in self.start_path.lower() for signal in DOC_PATH_SIGNALS):
            return False
        return any(signal in path for signal in DOC_PATH_SIGNALS)


__all__ = ["LinkTraversalFrontier"]
