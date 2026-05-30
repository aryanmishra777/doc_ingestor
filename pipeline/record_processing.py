"""Per-future and per-record processing for the crawl loop.

When a fetch future completes, its raw records must be: counted (failures), mined for
links (to grow the frontier), and individually cleaned, de-duplicated and accepted. This
module holds that logic so :mod:`pipeline.crawler` stays a tight orchestration loop.

``_process_raw_record`` keeps its original positional signature (and threaded skip
counters) because it is called directly by the test suite.
"""
from __future__ import annotations

from collections.abc import Callable

from cleaning import clean_record
from domain.records import DocPageRecord
from pipeline.dedup import _is_navigation_only_record, _try_accept_record
from pipeline.stats import CrawlAccumulator
from traversal import LinkTraversalFrontier

#: Emit a progress line every N accepted pages.
PROGRESS_LOG_INTERVAL = 10


def _process_done_futures(
    done: set,
    in_flight: dict,
    frontier: LinkTraversalFrontier,
    acc: CrawlAccumulator,
    log: Callable[[str], None],
    include_sparse_pages: bool,
    max_depth: int | None,
) -> None:
    """Drain completed futures: count failures, grow the frontier, accept records."""
    for future in done:
        url, depth = in_flight.pop(future)
        try:
            raw_records = future.result()
        except Exception as exc:
            acc.failed_pages += 1
            log(f"Failed: {url}: {exc}")
            continue

        log(f"Analysis: fetching page {len(acc.records) + 1} at depth {depth}: {url}")
        if _has_record_errors(raw_records):
            acc.failed_pages += 1
        if _update_frontier_with_links(frontier, url, depth, raw_records, max_depth):
            acc.depth_cap_reached = True

        for raw_record in raw_records:
            accepted, acc.skipped_by_canonical, acc.skipped_by_content_hash = _process_raw_record(
                raw_record, url, log, acc.records,
                acc.seen_canonical_urls, acc.seen_content_hashes,
                acc.skipped_by_canonical, acc.skipped_by_content_hash,
                include_sparse_pages=include_sparse_pages,
            )
            if accepted:
                acc.max_observed_depth = max(acc.max_observed_depth, depth)
                _maybe_log_progress(acc.records, depth, frontier, log)


def _process_raw_record(
    raw_record: DocPageRecord,
    url: str,
    log: Callable[[str], None],
    records: list[DocPageRecord],
    seen_canonical_urls: set[str],
    seen_content_hashes: set[str],
    skipped_by_canonical: int,
    skipped_by_content_hash: int,
    include_sparse_pages: bool = False,
) -> tuple[bool, int, int]:
    """Clean, de-duplicate and (maybe) accept one record; return acceptance + counters."""
    if _is_navigation_only_record(raw_record):
        if not include_sparse_pages:
            log(f"Analysis: using navigation-only page for discovery, not output: {url}")
            return False, skipped_by_canonical, skipped_by_content_hash
        log(f"Analysis: including navigation-only page in output (--include-sparse): {url}")

    cleaned_record = clean_record(raw_record)
    skip_reason = _try_accept_record(cleaned_record, records, seen_canonical_urls, seen_content_hashes)
    if skip_reason == "canonical":
        skipped_by_canonical += 1
        if skipped_by_canonical <= 5:
            log(f"Analysis: skipping duplicate canonical URL: {cleaned_record.get('canonical_url')}")
        return False, skipped_by_canonical, skipped_by_content_hash
    if skip_reason == "content_hash":
        skipped_by_content_hash += 1
        if skipped_by_content_hash <= 5:
            log(f"Analysis: skipping near-duplicate content page: {cleaned_record.get('url', url)}")
        return False, skipped_by_canonical, skipped_by_content_hash
    return True, skipped_by_canonical, skipped_by_content_hash


def _has_record_errors(raw_records: list[DocPageRecord]) -> bool:
    """Whether any record in the batch carries an extraction error."""
    return any(r.get("errors") for r in raw_records)


def _update_frontier_with_links(
    frontier: LinkTraversalFrontier,
    url: str,
    depth: int,
    raw_records: list[DocPageRecord],
    max_depth: int | None,
) -> bool:
    """Feed discovered links to the frontier; return True if a depth cap was hit here."""
    all_links = [lnk for r in raw_records for lnk in r.get("links", [])]
    depth_cap_reached = max_depth is not None and depth >= max_depth and bool(all_links)
    frontier.register_discovered_links(source_url=url, new_links=all_links, current_depth=depth)
    return depth_cap_reached


def _maybe_log_progress(
    records: list[DocPageRecord],
    depth: int,
    frontier: LinkTraversalFrontier,
    log: Callable[[str], None],
) -> None:
    """Emit a periodic progress line on every :data:`PROGRESS_LOG_INTERVAL`-th page."""
    if len(records) % PROGRESS_LOG_INTERVAL == 0:
        log(f"Analysis progress: pages={len(records)}, current_depth={depth}, queued={len(frontier.queue)}")


__all__ = ["_process_done_futures", "_process_raw_record"]
