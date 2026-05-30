"""Value objects for crawl results and mutable crawl bookkeeping.

:class:`PipelineStats` and :class:`PipelineResult` are frozen result types returned to
callers. :class:`CrawlAccumulator` is the mutable scratchpad threaded through the crawl
loop — it holds the accepted records plus the de-duplication sets and counters that would
otherwise be a fistful of loose local variables.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from domain.records import DocPageRecord


@dataclass(frozen=True)
class PipelineStats:
    """Summary metrics describing how a crawl terminated."""

    pages: int
    required_depth: int
    failed_pages: int
    truncated_by_page_cap: bool
    depth_cap_reached: bool


@dataclass(frozen=True)
class PipelineResult:
    """A rendered crawl: the Markdown plus the records and stats it came from."""

    markdown: str
    records: list[DocPageRecord]
    stats: PipelineStats


@dataclass
class CrawlAccumulator:
    """Mutable state accumulated while the crawl loop runs."""

    records: list[DocPageRecord] = field(default_factory=list)
    seen_canonical_urls: set[str] = field(default_factory=set)
    seen_content_hashes: set[str] = field(default_factory=set)
    failed_pages: int = 0
    max_observed_depth: int = 0
    depth_cap_reached: bool = False
    skipped_by_canonical: int = 0
    skipped_by_content_hash: int = 0


__all__ = ["PipelineStats", "PipelineResult", "CrawlAccumulator"]
