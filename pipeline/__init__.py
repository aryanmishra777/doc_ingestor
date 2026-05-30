"""Public facade for crawling documentation and writing Markdown output."""
from __future__ import annotations

from pipeline.crawler import collect_records, run_pipeline, run_pipeline_result
from pipeline.dedup import (
    _is_navigation_only_record,
    _normalize_canonical_url,
    _record_content_hash,
    _try_accept_record,
)
from pipeline.output import DEFAULT_CHUNK_PAGES, write_markdown_outputs
from pipeline.record_processing import _process_done_futures, _process_raw_record
from pipeline.stats import CrawlAccumulator, PipelineResult, PipelineStats

__all__ = [
    "DEFAULT_CHUNK_PAGES",
    "CrawlAccumulator",
    "PipelineResult",
    "PipelineStats",
    "collect_records",
    "run_pipeline",
    "run_pipeline_result",
    "write_markdown_outputs",
    "_is_navigation_only_record",
    "_normalize_canonical_url",
    "_process_done_futures",
    "_process_raw_record",
    "_record_content_hash",
    "_try_accept_record",
]
