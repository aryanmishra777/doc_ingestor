"""De-duplication and record-acceptance logic.

Large doc sites serve the same content under many URLs (trailing slashes, canonical
aliases, mirrored pages). Two guards prevent duplicates in the output: a normalized
*canonical URL* set and a *content hash* set. :func:`_try_accept_record` applies both and
appends the record only if it is new. :func:`_is_navigation_only_record` identifies
link-only pages that are useful for discovery but (by default) not for output.
"""
from __future__ import annotations

import hashlib
from urllib.parse import urlparse, urlunparse

from domain.records import DocPageRecord


def _normalize_canonical_url(url: str | None) -> str:
    """Canonicalize a URL for duplicate detection (scheme/host lower, no trailing slash)."""
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def _is_navigation_only_record(record: DocPageRecord) -> bool:
    """A page with links but no content/code and no errors — useful only for discovery."""
    return (
        not record.get("content_blocks")
        and not record.get("code_blocks")
        and bool(record.get("links"))
        and not record.get("errors")
    )


def _record_content_hash(record: DocPageRecord) -> str:
    """A stable SHA-256 over a record's title + textual content, for near-dup detection."""
    parts: list[str] = [record.get("title", "")]
    for block in record.get("content_blocks", []):
        parts.append(block.get("type", ""))
        parts.append(block.get("text", ""))
        items = block.get("items") or []
        if items:
            parts.append("\n".join(items))
        rows = block.get("rows") or []
        if rows:
            parts.append("\n".join("|".join(row) for row in rows))
    for code_block in record.get("code_blocks", []):
        parts.append(code_block.get("language") or "")
        parts.append(code_block.get("text", ""))
    payload = "\n\n".join(parts).encode("utf-8", errors="ignore")
    return hashlib.sha256(payload).hexdigest()


def _try_accept_record(
    cleaned: DocPageRecord,
    records: list[DocPageRecord],
    seen_canonical_urls: set[str],
    seen_content_hashes: set[str],
) -> str | None:
    """Append ``cleaned`` if new; else return why it was skipped.

    Returns ``"canonical"`` or ``"content_hash"`` for a duplicate, or ``None`` after
    accepting and registering the record's canonical URL and content hash.
    """
    canonical_url = _normalize_canonical_url(cleaned.get("canonical_url"))
    if canonical_url and canonical_url in seen_canonical_urls:
        return "canonical"
    content_hash = _record_content_hash(cleaned)
    if content_hash in seen_content_hashes:
        return "content_hash"
    if canonical_url:
        seen_canonical_urls.add(canonical_url)
    seen_content_hashes.add(content_hash)
    records.append(cleaned)
    return None


__all__ = [
    "_normalize_canonical_url",
    "_is_navigation_only_record",
    "_record_content_hash",
    "_try_accept_record",
]
