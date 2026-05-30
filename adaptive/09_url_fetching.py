

"""Adaptive URL-list fetching and OpenAPI record builders.

Builds readable API operation sections, fetches selected documentation URLs in parallel,
and filters sparse records before quality evaluation.
"""

def _build_param_lines(parameters: list[Any]) -> list[str]:
    return [
        f"{p['name']} ({p.get('in', '')}, {'required' if p.get('required') else 'optional'}): {p.get('description', '')}".strip(": ")
        for p in parameters
        if isinstance(p, dict) and p.get("name")
    ]


def _build_response_lines(responses: dict[str, Any]) -> list[str]:
    return [
        f"{code}: {resp.get('description', '')}"
        for code, resp in responses.items()
        if isinstance(resp, dict)
    ]


def _build_operation_record(
    operation: dict[str, Any],
    method: str,
    path: str,
    spec_url: str,
    api_title: str,
    source_domain: str | None,
    idx: int,
) -> DocPageRecord:
    summary = operation.get("summary", "")
    description = operation.get("description", "")
    tags = operation.get("tags", [])

    title = f"{method.upper()} {path}"
    if summary:
        title = f"{title} — {summary}"

    content_blocks: list[ContentBlock] = []
    if description:
        content_blocks.append({"type": "paragraph", "text": description})
    if tags:
        content_blocks.append({"type": "paragraph", "text": f"Tags: {', '.join(tags)}"})

    param_lines = _build_param_lines(operation.get("parameters", []))
    if param_lines:
        content_blocks.append({"type": "list", "text": "Parameters", "items": param_lines})

    resp_lines = _build_response_lines(operation.get("responses", {}))
    if resp_lines:
        content_blocks.append({"type": "list", "text": "Responses", "items": resp_lines})

    anchor = re.sub(r"[^a-z0-9]+", "-", f"{method}-{path}".lower()).strip("-")
    return {
        "url": f"{spec_url}#{anchor}",
        "canonical_url": f"{spec_url}#{anchor}",
        "depth": 0,
        "order_index": idx,
        "title": title,
        "content_blocks": content_blocks,
        "code_blocks": [],
        "links": [],
        "metadata": {"source_domain": source_domain, "breadcrumbs": [api_title] + tags},
        "errors": [],
    }


# ---------------------------------------------------------------------------
# Shared URL-list fetcher (sitemap and llms.txt link paths)
# ---------------------------------------------------------------------------

def _fetch_one(url: str, idx: int) -> list[DocPageRecord]:
    path_lower = urlparse(url).path.lower()
    if path_lower.endswith((".md", ".markdown")):
        return extract_markdown(url, depth=0, order_index=idx)
    if path_lower.endswith(".pdf"):
        return extract_pdf(url, depth=0, order_index=idx)
    r = _http_get(url, read_limit=PAGE_READ_LIMIT, timeout=PAGE_FETCH_TIMEOUT)
    if r and r["status"] == 200:
        return [extract_from_html(r["body"], url=url, depth=0, order_index=idx)]
    status = r["status"] if r else "connection failed"
    return [make_error_record(url, 0, idx, f"HTTP {status}", None)]


def _is_sparse_record(record: DocPageRecord) -> bool:
    return not record.get("content_blocks") and not record.get("code_blocks")


def _fetch_url_list(
    urls: list[str],
    max_workers: int,
    log: Callable[[str], None],
    include_sparse_pages: bool = False,
) -> list[DocPageRecord]:
    records: list[DocPageRecord] = []
    seen_urls: set[str] = set()
    total = len(urls)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(_fetch_one, url, idx): url
            for idx, url in enumerate(urls)
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                raw_records = future.result()
            except Exception as exc:
                log(f"Adaptive: failed to fetch {url}: {exc}")
                continue
            for raw in raw_records:
                cleaned = clean_record(raw)
                record_url = cleaned.get("url", "")
                if not record_url or record_url in seen_urls:
                    continue
                if not include_sparse_pages and _is_sparse_record(cleaned):
                    log(f"Adaptive: skipping navigation-only page: {record_url}")
                    continue
                seen_urls.add(record_url)
                records.append(cleaned)
                if len(records) % 10 == 0:
                    log(f"Adaptive: fetched {len(records)}/{total} pages...")
    return records
