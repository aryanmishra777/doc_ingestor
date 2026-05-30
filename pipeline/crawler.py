"""Concurrent crawl orchestration.

This module is the pipeline facade's main worker: it owns the frontier, browser pool,
executor, and result assembly while delegating fetching, record processing, logging, and
stats to smaller modules.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait as futures_wait

from domain.records import DocPageRecord
from pipeline.browser_pool import BrowserPool
from pipeline.fetch_dispatch import page_fetch
from pipeline.log import stderr_logger
from pipeline.record_processing import _process_done_futures
from pipeline.stats import CrawlAccumulator, PipelineResult, PipelineStats
from structuring import structure_records_to_markdown
from traversal import LinkTraversalFrontier


def run_pipeline(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    logger: Callable[[str], None] | None = None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
) -> str:
    """Crawl ``start_url`` and return rendered NotebookLM-ready Markdown."""
    records, _ = collect_records(
        start_url, max_pages=max_pages, max_depth=max_depth, logger=logger,
        max_workers=max_workers, include_sparse_pages=include_sparse_pages,
    )
    return structure_records_to_markdown(records)


def run_pipeline_result(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    logger: Callable[[str], None] | None = None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
) -> PipelineResult:
    """Crawl ``start_url`` and return Markdown, records, and crawl stats."""
    records, stats = collect_records(
        start_url, max_pages=max_pages, max_depth=max_depth, logger=logger,
        max_workers=max_workers, include_sparse_pages=include_sparse_pages,
    )
    return PipelineResult(markdown=structure_records_to_markdown(records), records=records, stats=stats)


def collect_records(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    logger: Callable[[str], None] | None = None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
) -> tuple[list[DocPageRecord], PipelineStats]:
    """Crawl from ``start_url`` and return cleaned records plus crawl statistics."""
    log = logger or stderr_logger
    _log_crawl_limits(log, max_pages, max_depth)

    frontier = LinkTraversalFrontier(start_url, max_pages=max_pages, max_depth=max_depth)
    pool = BrowserPool()
    acc = CrawlAccumulator()
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        in_flight: dict = {}
        while True:
            _fill_executor(in_flight, executor, frontier, pool, acc, max_workers)
            if not in_flight:
                break
            done, _ = futures_wait(list(in_flight.keys()), return_when=FIRST_COMPLETED)
            _process_done_futures(done, in_flight, frontier, acc, log, include_sparse_pages, max_depth)
    except KeyboardInterrupt:
        log("Interrupted: cancelling in-flight fetches...")
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        executor.shutdown(wait=False)
        pool.close_all()

    return acc.records, _finish_stats(acc, frontier, log)


def _fill_executor(
    in_flight: dict,
    executor: ThreadPoolExecutor,
    frontier: LinkTraversalFrontier,
    pool: BrowserPool,
    acc: CrawlAccumulator,
    max_workers: int,
) -> None:
    """Submit queued URLs until all workers are busy or the frontier is empty."""
    while len(in_flight) < max_workers:
        url, depth = frontier.get_next_url()
        if url is None:
            break
        order_index = len(acc.records) + len(in_flight)
        future = executor.submit(page_fetch, url, depth, order_index, pool)
        in_flight[future] = (url, depth)


def _finish_stats(
    acc: CrawlAccumulator,
    frontier: LinkTraversalFrontier,
    log: Callable[[str], None],
) -> PipelineStats:
    """Log final crawl notes and build the immutable stats object."""
    truncated = bool(frontier.queue)
    log(
        "Analysis complete: "
        f"pages={len(acc.records)}, required_depth={acc.max_observed_depth}, "
        f"failed_pages={acc.failed_pages}, truncated_by_page_cap={truncated}, "
        f"depth_cap_reached={acc.depth_cap_reached}, "
        f"skipped_by_canonical={acc.skipped_by_canonical}, "
        f"skipped_by_content_hash={acc.skipped_by_content_hash}"
    )
    if truncated:
        log("Analysis note: more pages were still queued. Increase --max-pages or --max-depth if you want a broader crawl.")
    if acc.depth_cap_reached:
        log("Analysis note: pages at the maximum depth still had outgoing links. Increase --max-depth if you want to crawl deeper.")
    return PipelineStats(
        pages=len(acc.records),
        required_depth=acc.max_observed_depth,
        failed_pages=acc.failed_pages,
        truncated_by_page_cap=truncated,
        depth_cap_reached=acc.depth_cap_reached,
    )


def _log_crawl_limits(log: Callable[[str], None], max_pages: int | None, max_depth: int | None) -> None:
    """Emit the crawl limit line used by the CLI."""
    if max_pages is None and max_depth is None:
        log("Analysis: complete discovery enabled (no limits)")
        return
    if max_pages is None or max_depth is None:
        limits = [f"{name}={value}" for name, value in (("max_pages", max_pages), ("max_depth", max_depth)) if value is not None]
        log(f"Analysis: crawling with limits ({', '.join(limits)})")
        return
    log(f"Analysis: crawling with limits (max_pages={max_pages}, max_depth={max_depth})")


__all__ = ["collect_records", "run_pipeline", "run_pipeline_result"]
