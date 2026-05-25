from __future__ import annotations

from collections import deque
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
    "referral",
    "source",
}

DOC_PATH_SIGNALS = (
    "/docs",
    "/documentation",
    "/reference",
    "/guide",
    "/api",
    "/learn",
    "/manual",
    "/tutorial",
)

EXCLUDED_PATH_SIGNALS = (
    "/blog",
    "/login",
    "/signup",
    "/pricing",
    "/careers",
    "/contact",
    "/support/tickets",
)

ASSET_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".css",
    ".js",
    ".map",
    ".zip",
    ".tar",
    ".gz",
    ".mp4",
    ".mov",
    ".avi",
)


class LinkTraversalFrontier:
    def __init__(self, start_url: str, max_pages: int | None = None, max_depth: int | None = None):
        self.start_url = self._normalize_url(start_url, None)
        parsed_start = urlparse(self.start_url)
        self.allowed_domain = parsed_start.netloc
        # Lowercased to match the lowercased `path` used in _is_relevant_edge comparisons.
        self.start_path = (parsed_start.path.rstrip("/") or "/").lower()
        self.queue: deque[tuple[str, int]] = deque([(self.start_url, 0)])
        self.seen = {self.start_url}
        self.pages_yielded = 0
        self.max_pages = max_pages
        self.max_depth = max_depth

    def get_next_url(self) -> tuple[str | None, int]:
        if not self.queue:
            return None, -1
        if self.max_pages is not None and self.pages_yielded >= self.max_pages:
            return None, -1

        next_url, depth = self.queue.popleft()
        self.pages_yielded += 1
        return next_url, depth

    def register_discovered_links(
        self,
        source_url: str,
        new_links: list[str],
        current_depth: int,
    ) -> None:
        if self.max_depth is not None and current_depth >= self.max_depth:
            return

        for raw_link in new_links:
            normalized_link = self._normalize_url(raw_link, source_url)
            if not normalized_link or normalized_link in self.seen:
                continue
            if not self._is_relevant_edge(normalized_link):
                continue
            self.seen.add(normalized_link)
            self.queue.append((normalized_link, current_depth + 1))

    def _normalize_url(self, raw_url: str, source_url: str | None) -> str:
        if not raw_url:
            return ""

        absolute_url = urljoin(source_url or raw_url, raw_url)
        parsed = urlparse(absolute_url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return ""

        path = parsed.path.rstrip("/") or "/"
        kept_query_pairs = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_QUERY_KEYS
        ]
        clean_query = urlencode(kept_query_pairs, doseq=True)
        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                "",
                clean_query,
                "",
            )
        )

    def _is_relevant_edge(self, url: str) -> bool:
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
        # Only use the doc-signal fallback when the start URL is above the docs tree.
        # If start_path already contains a signal (e.g. /docs/Web/JavaScript), the
        # fallback would let the crawler escape into sibling subtrees (URL explosion).
        if any(signal in self.start_path.lower() for signal in DOC_PATH_SIGNALS):
            return False
        return any(signal in path for signal in DOC_PATH_SIGNALS)
