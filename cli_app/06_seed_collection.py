

"""Seed crawling and output fan-out helpers.

Collects records for one or more seed URLs, de-duplicates merged results, and writes
separate per-seed outputs when requested by the CLI.
"""

def collect_records_for_seeds(
    seed_urls: list[str],
    max_pages: int | None,
    max_depth: int | None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
    adaptive: bool = False,
    adaptive_model: str = DEFAULT_ADAPTIVE_MODEL,
    adaptive_provider: str = "cloud",
) -> list[DocPageRecord]:
    all_records: list[DocPageRecord] = []
    seen_urls: set[str] = set()
    seen_canonical_urls: set[str] = set()

    for seed_url in seed_urls:
        records = _collect_seed_records(
            seed_url,
            max_pages=max_pages,
            max_depth=max_depth,
            max_workers=max_workers,
            include_sparse_pages=include_sparse_pages,
            adaptive=adaptive,
            adaptive_model=adaptive_model,
            adaptive_provider=adaptive_provider,
        )
        if records is None:
            continue
        for record in records:
            _append_if_unique_record(
                record,
                all_records,
                seen_urls=seen_urls,
                seen_canonical_urls=seen_canonical_urls,
            )

    return all_records


def _append_if_unique_record(
    record: DocPageRecord,
    all_records: list[DocPageRecord],
    seen_urls: set[str],
    seen_canonical_urls: set[str],
) -> None:
    canonical_url = (record.get("canonical_url") or "").strip()
    record_url = (record.get("url") or "").strip()

    if canonical_url and canonical_url in seen_canonical_urls:
        return
    if record_url and record_url in seen_urls:
        return

    if canonical_url:
        seen_canonical_urls.add(canonical_url)
    if record_url:
        seen_urls.add(record_url)
    all_records.append(record)


def write_outputs_per_seed(
    seed_urls: list[str],
    output: Path,
    max_pages: int | None,
    max_depth: int | None,
    chunk_pages: int,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
    adaptive: bool = False,
    adaptive_model: str = DEFAULT_ADAPTIVE_MODEL,
    adaptive_provider: str = "cloud",
) -> None:
    total = len(seed_urls)
    for index, seed_url in enumerate(seed_urls, start=1):
        records = _collect_seed_records(
            seed_url,
            max_pages=max_pages,
            max_depth=max_depth,
            max_workers=max_workers,
            include_sparse_pages=include_sparse_pages,
            adaptive=adaptive,
            adaptive_model=adaptive_model,
            adaptive_provider=adaptive_provider,
        )
        if records is None:
            continue
        seed_output = _build_seed_output_path(output, seed_url, index=index, total=total)
        write_markdown_outputs(records, seed_output, chunk_pages=chunk_pages)


def _collect_seed_records(
    seed_url: str,
    max_pages: int | None,
    max_depth: int | None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
    adaptive: bool = False,
    adaptive_model: str = DEFAULT_ADAPTIVE_MODEL,
    adaptive_provider: str = "cloud",
) -> list[DocPageRecord] | None:
    try:
        if adaptive:
            records, _ = collect_records_adaptive(
                seed_url,
                max_pages=max_pages,
                max_depth=max_depth,
                max_workers=max_workers,
                include_sparse_pages=include_sparse_pages,
                llm_model=adaptive_model,
                llm_provider=adaptive_provider,
            )
        else:
            records, _ = collect_records(
                seed_url,
                max_pages=max_pages,
                max_depth=max_depth,
                max_workers=max_workers,
                include_sparse_pages=include_sparse_pages,
            )
        return records
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"Seed crawl failed for {seed_url}: {exc}", file=sys.stderr)
        return None
