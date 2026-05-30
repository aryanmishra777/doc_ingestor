"""URL normalization rules and the constant sets that bound a crawl.

Normalization makes two URLs that point at the same page compare equal: lower-cased
scheme/host, trailing slash removed, and tracking query params (utm_*, gclid, …) stripped
while meaningful query params are kept. The constant tuples classify links during
relevance filtering — which extensions are assets to ignore, which path segments are
off-topic (blog/login/…), and which segments positively signal documentation.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

#: Query keys that identify the *same* page (analytics/referral noise) — dropped.
TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid", "ref", "referral", "source",
}

#: Path segments that positively signal documentation content.
DOC_PATH_SIGNALS = (
    "/docs", "/documentation", "/reference", "/guide",
    "/api", "/learn", "/manual", "/tutorial",
)

#: Path segments that mark a URL as off-topic for a docs crawl.
EXCLUDED_PATH_SIGNALS = (
    "/blog", "/login", "/signup", "/pricing", "/careers", "/contact", "/support/tickets",
)

#: File extensions that are assets, never documentation pages.
ASSET_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".css", ".js",
    ".map", ".zip", ".tar", ".gz", ".mp4", ".mov", ".avi",
)


def normalize_url(raw_url: str, source_url: str | None) -> str:
    """Resolve ``raw_url`` against ``source_url`` and canonicalize it.

    Returns ``""`` for empty input or non-``http(s)`` schemes (mailto, javascript, …), so
    callers can treat the empty string as "not a crawlable URL".
    """
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
        (parsed.scheme.lower(), parsed.netloc.lower(), path, "", clean_query, "")
    )


__all__ = [
    "TRACKING_QUERY_KEYS",
    "DOC_PATH_SIGNALS",
    "EXCLUDED_PATH_SIGNALS",
    "ASSET_EXTENSIONS",
    "normalize_url",
]
