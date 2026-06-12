

"""Deterministic handler: OpenAPI / Swagger.

Converts OpenAPI operations into structured records when the probe discovers an API spec.
"""

def _handle_convert_openapi(state: AgentState, log: Callable[[str], None]) -> None:
    content = state.detection.prefetched_content or ""
    if not content:
        r = _http_get(state.detection.url, read_limit=4 * 1024 * 1024)
        content = r["body"] if r and r["status"] == 200 else ""

    if not content:
        log("Adaptive: OpenAPI spec empty or unreadable, falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return

    try:
        spec = json.loads(content)
    except json.JSONDecodeError:
        log("Adaptive: OpenAPI spec is not valid JSON, falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return

    records = _convert_openapi_to_records(spec, state.detection.url)
    if not records:
        log("Adaptive: OpenAPI spec yielded no records, falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return

    log(f"Adaptive: converted {len(records)} endpoint records from OpenAPI spec")
    state.doc_records = records
    state.phase = CrawlerPhase.EVALUATE_QUALITY


def _convert_openapi_to_records(spec: dict[str, Any], spec_url: str) -> list[DocPageRecord]:
    api_title = spec.get("info", {}).get("title", "API")
    source_domain = urlparse(spec_url).netloc or None
    _HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
    records: list[DocPageRecord] = []

    for idx, (path, path_item) in enumerate(spec.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            record = _build_operation_record(
                operation, method, path, spec_url, api_title, source_domain, idx
            )
            records.append(record)

    return records