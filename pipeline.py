from __future__ import annotations

import hashlib
import sys
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait as futures_wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

try:
    from .cleaning import clean_record
    from .extraction import extract_page, extract_page_in_browser
    from .markdown_extraction import extract_markdown
    from .models import DocPageRecord
    from .pdf_extraction import extract_pdf
    from .structuring import derive_title, structure_records_to_markdown
    from .traversal import LinkTraversalFrontier
except ImportError:
    from cleaning import clean_record
    from extraction import extract_page, extract_page_in_browser
    from markdown_extraction import extract_markdown
    from models import DocPageRecord
    from pdf_extraction import extract_pdf
    from structuring import derive_title, structure_records_to_markdown
    from traversal import LinkTraversalFrontier


DEFAULT_CHUNK_PAGES = 50
PROGRESS_LOG_INTERVAL = 10


@dataclass(frozen=True)
class PipelineStats:
    pages: int
    required_depth: int
    failed_pages: int
    truncated_by_page_cap: bool
    depth_cap_reached: bool


@dataclass(frozen=True)
class PipelineResult:
    markdown: str
    records: list[DocPageRecord]
    stats: PipelineStats


@dataclass
class _CrawlAccumulator:
    records: list[DocPageRecord] = field(default_factory=list)
    seen_canonical_urls: set[str] = field(default_factory=set)
    seen_content_hashes: set[str] = field(default_factory=set)
    failed_pages: int = 0
    max_observed_depth: int = 0
    depth_cap_reached: bool = False
    skipped_by_canonical: int = 0
    skipped_by_content_hash: int = 0


class _BrowserPool:
    def __init__(self) -> None:
        self._tls = threading.local()
        self._browsers: list[tuple[Any, Any]] = []
        self._lock = threading.Lock()

    def get(self) -> Any:
        if not hasattr(self._tls, "browser"):
            self._tls.browser = self._launch()
        return self._tls.browser

    def _launch(self) -> Any:
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            self._tls.pw = pw
            with self._lock:
                self._browsers.append((pw, browser))
            return browser
        except Exception:
            return None

    def close_all(self) -> None:
        with self._lock:
            for pw, browser in self._browsers:
                _silent_call(browser, "close")
                _silent_call(pw, "stop")
            self._browsers.clear()


def _silent_call(obj: Any, method: str) -> None:
    try:
        getattr(obj, method)()
    except Exception:
        pass


def run_pipeline(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    logger: Callable[[str], None] | None = None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
) -> str:
    records, _ = collect_records(start_url, max_pages=max_pages, max_depth=max_depth, logger=logger, max_workers=max_workers, include_sparse_pages=include_sparse_pages)
    return structure_records_to_markdown(records)


def run_pipeline_result(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    logger: Callable[[str], None] | None = None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
) -> PipelineResult:
    records, stats = collect_records(start_url, max_pages=max_pages, max_depth=max_depth, logger=logger, max_workers=max_workers, include_sparse_pages=include_sparse_pages)
    return PipelineResult(
        markdown=structure_records_to_markdown(records),
        records=records,
        stats=stats,
    )


def collect_records(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    logger: Callable[[str], None] | None = None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
) -> tuple[list[DocPageRecord], PipelineStats]:
    log = logger or _stderr_logger
    _log_crawl_limits(log, max_pages, max_depth)

    frontier = LinkTraversalFrontier(start_url, max_pages=max_pages, max_depth=max_depth)
    pool = _BrowserPool()
    acc = _CrawlAccumulator()

    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        in_flight: dict = {}
        while True:
            while len(in_flight) < max_workers:
                url, depth = frontier.get_next_url()
                if url is None:
                    break
                order_index = len(acc.records) + len(in_flight)
                future = executor.submit(_page_fetch, url, depth, order_index, pool)
                in_flight[future] = (url, depth)

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
        log(
            "Analysis note: more pages were still queued. Increase --max-pages "
            "or --max-depth if you want a broader crawl."
        )
    if acc.depth_cap_reached:
        log(
            "Analysis note: pages at the maximum depth still had outgoing links. "
            "Increase --max-depth if you want to crawl deeper."
        )

    stats = PipelineStats(
        pages=len(acc.records),
        required_depth=acc.max_observed_depth,
        failed_pages=acc.failed_pages,
        truncated_by_page_cap=truncated,
        depth_cap_reached=acc.depth_cap_reached,
    )
    return acc.records, stats


def _page_fetch(
    url: str, depth: int, order_index: int, pool: _BrowserPool
) -> list[DocPageRecord]:
    if _is_pdf_url(url):
        return extract_pdf(url, depth=depth, order_index=order_index)
    if _is_markdown_url(url):
        return extract_markdown(url, depth=depth, order_index=order_index)
    browser = pool.get()
    if browser is None:
        return [extract_page(url, depth=depth, order_index=order_index)]
    return [extract_page_in_browser(browser, url, depth=depth, order_index=order_index)]


def _process_done_futures(
    done: set,
    in_flight: dict,
    frontier: LinkTraversalFrontier,
    acc: _CrawlAccumulator,
    log: Callable[[str], None],
    include_sparse_pages: bool,
    max_depth: int | None,
) -> None:
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


def _maybe_log_progress(
    records: list[DocPageRecord],
    depth: int,
    frontier: LinkTraversalFrontier,
    log: Callable[[str], None],
) -> None:
    if len(records) % PROGRESS_LOG_INTERVAL == 0:
        log(
            "Analysis progress: "
            f"pages={len(records)}, current_depth={depth}, queued={len(frontier.queue)}"
        )


def _log_crawl_limits(
    log: Callable[[str], None],
    max_pages: int | None,
    max_depth: int | None,
) -> None:
    if max_pages is None and max_depth is None:
        log("Analysis: complete discovery enabled (no limits)")
        return
    if max_pages is None or max_depth is None:
        limits: list[str] = []
        if max_pages is not None:
            limits.append(f"max_pages={max_pages}")
        if max_depth is not None:
            limits.append(f"max_depth={max_depth}")
        log(f"Analysis: crawling with limits ({', '.join(limits)})")
        return
    log(f"Analysis: crawling with limits (max_pages={max_pages}, max_depth={max_depth})")


def _has_record_errors(raw_records: list[DocPageRecord]) -> bool:
    return any(r.get("errors") for r in raw_records)


def _update_frontier_with_links(
    frontier: LinkTraversalFrontier,
    url: str,
    depth: int,
    raw_records: list[DocPageRecord],
    max_depth: int | None,
) -> bool:
    all_links = [lnk for r in raw_records for lnk in r.get("links", [])]
    depth_cap_reached = max_depth is not None and depth >= max_depth and bool(all_links)
    frontier.register_discovered_links(
        source_url=url,
        new_links=all_links,
        current_depth=depth,
    )
    return depth_cap_reached


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
    if _is_navigation_only_record(raw_record):
        if not include_sparse_pages:
            log(f"Analysis: using navigation-only page for discovery, not output: {url}")
            return False, skipped_by_canonical, skipped_by_content_hash
        log(f"Analysis: including navigation-only page in output (--include-sparse): {url}")

    cleaned_record = clean_record(raw_record)
    skip_reason = _try_accept_record(
        cleaned_record, records, seen_canonical_urls, seen_content_hashes
    )
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


def write_markdown_outputs(
    records: list[DocPageRecord],
    output: Path,
    chunk_pages: int = DEFAULT_CHUNK_PAGES,
    logger: Callable[[str], None] | None = None,
) -> list[Path]:
    log = logger or _stderr_logger
    if chunk_pages <= 0:
        raise ValueError("chunk_pages must be greater than zero")

    chunks = _chunk_records(records, chunk_pages)
    if len(chunks) <= 1:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(structure_records_to_markdown(records), encoding="utf-8")
        log(f"Output: wrote 1 Markdown file to {output}")
        return [output]

    output_dir = _chunk_output_dir(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output.stem if output.suffix else "documentation"
    written_paths: list[Path] = []
    total_chunks = len(chunks)

    log(
        "Output: chunking Markdown "
        f"into {total_chunks} files with up to {chunk_pages} pages each"
    )
    for index, chunk in enumerate(chunks, start=1):
        chunk_path = output_dir / f"{prefix}_part_{index:03d}_of_{total_chunks:03d}.md"
        title = f"{derive_title(records)} (Part {index} of {total_chunks})"
        chunk_path.write_text(structure_records_to_markdown(chunk, title=title), encoding="utf-8")
        written_paths.append(chunk_path)
        log(f"Output: wrote chunk {index}/{total_chunks}: {chunk_path}")

    log(f"Output complete: wrote {len(written_paths)} Markdown files in {output_dir}")
    return written_paths


def _stderr_logger(message: str) -> None:
    print(message, file=sys.stderr)


def _chunk_records(records: list[DocPageRecord], chunk_pages: int) -> list[list[DocPageRecord]]:
    if not records:
        return [[]]
    return [records[index : index + chunk_pages] for index in range(0, len(records), chunk_pages)]


def _chunk_output_dir(output: Path) -> Path:
    if output.suffix:
        return output.parent / f"{output.stem}_chunks"
    return output


def _normalize_canonical_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))



def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _is_markdown_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith((".md", ".markdown"))


def _try_accept_record(
    cleaned: DocPageRecord,
    records: list[DocPageRecord],
    seen_canonical_urls: set[str],
    seen_content_hashes: set[str],
) -> str | None:
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


def _is_navigation_only_record(record: DocPageRecord) -> bool:
    return (
        not record.get("content_blocks")
        and not record.get("code_blocks")
        and bool(record.get("links"))
        and not record.get("errors")
    )


def _record_content_hash(record: DocPageRecord) -> str:
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
