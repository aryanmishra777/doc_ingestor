

"""Sitemap URL filtering and OpenAPI conversion.

Filters sitemap URLs for the current documentation scope and converts OpenAPI operations
into structured records when the probe discovers an API spec.
"""

def _parse_sitemap_urls(
    sitemap_url: str,
    target_url: str,
    initial_body: str | None = None,
    max_urls: int | None = None,
) -> list[str]:
    parsed_target = urlparse(target_url)
    target_domain = parsed_target.netloc.lower()
    start_prefix = _sitemap_start_prefix(parsed_target.path)
    restrict_to_prefix = start_prefix != "/"

    visited: set[str] = set()
    queue = [sitemap_url]
    urls: list[str] = []

    while queue and len(visited) < MAX_SITEMAP_FILES and (max_urls is None or len(urls) < max_urls):
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        body = initial_body if current == sitemap_url else None
        if body is None:
            r = _http_get(current, read_limit=8 * 1024 * 1024, timeout=SITEMAP_TIMEOUT)
            if not r or r["status"] != 200:
                continue
            body = r["body"]

        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            continue

        _process_sitemap_document(root, target_domain, restrict_to_prefix, start_prefix, urls, queue, max_urls)

    return urls


def _is_sitemap_file_url(url: str) -> bool:
    leaf = urlparse(url).path.rsplit("/", 1)[-1].lower()
    return leaf.endswith(".xml") and "sitemap" in leaf


def _sitemap_start_prefix(path: str) -> str:
    normalized = (path or "/").lower()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return "/"

    # If the start URL's leaf segment is a file (e.g. user passed /sitemap.xml
    # or /en/latest/index.html), it is not a directory prefix — strip it so
    # the parent directory is used instead. Without this, the file path gets
    # appended with "/" and rejects every URL in the sitemap.
    if "." in parts[-1]:
        parts = parts[:-1]
        if not parts:
            return "/"

    docs_index = parts.index("docs") if "docs" in parts else -1
    if docs_index >= 0:
        if len(parts) == docs_index + 1:
            return "/" + "/".join(parts[: docs_index + 1]) + "/"
        next_part = parts[docs_index + 1]
        if next_part in {"home", "index", "overview", "documentation"}:
            return "/" + "/".join(parts[: docs_index + 1]) + "/"

    return "/" + "/".join(parts) + "/"


# ---------------------------------------------------------------------------
# Deterministic handler: OpenAPI / Swagger
# ---------------------------------------------------------------------------

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
