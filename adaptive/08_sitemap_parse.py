

"""Sitemap URL filtering.

Filters sitemap URLs for the current documentation scope. (OpenAPI conversion lives in
the ``17_openapi`` chunk.)
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

        body = _load_sitemap_body(current, sitemap_url, initial_body)
        if body is None:
            continue

        if not _parse_sitemap_document(body, target_domain, restrict_to_prefix, start_prefix, urls, queue, max_urls):
            continue

    if len(urls) <= 1 and initial_body:
        version_roots = _collect_version_root_urls(initial_body, parsed_target)
        if len(version_roots) > len(urls):
            return version_roots

    return urls


def _load_sitemap_body(current: str, sitemap_url: str, initial_body: str | None) -> str | None:
    if current == sitemap_url and initial_body is not None:
        return initial_body

    r = _http_get(current, read_limit=8 * 1024 * 1024, timeout=SITEMAP_TIMEOUT)
    if not r or r["status"] != 200:
        return None
    return r["body"]


def _parse_sitemap_document(
    body: str,
    target_domain: str,
    restrict_to_prefix: bool,
    start_prefix: str,
    urls: list[str],
    queue: list[str],
    max_urls: int | None,
) -> bool:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return False

    _process_sitemap_document(root, target_domain, restrict_to_prefix, start_prefix, urls, queue, max_urls)
    return True


def _collect_version_root_urls(body: str, parsed_target: ParseResult) -> list[str]:
    target_parts = [part for part in (parsed_target.path or "/").split("/") if part]
    if len(target_parts) < 2:
        return []

    target_domain = parsed_target.netloc.lower()
    expected_depth = len(target_parts)
    target_root = target_parts[0]
    version_roots: list[str] = []
    seen: set[str] = set()

    for loc in re.findall(r"<loc>\s*(.*?)\s*</loc>", body, flags=re.IGNORECASE):
        candidate = html.unescape(loc.strip())
        if not candidate or candidate in seen:
            continue
        parsed = urlparse(candidate)
        if parsed.netloc.lower() != target_domain:
            continue
        if not parsed.path.endswith("/"):
            continue
        if any(parsed.path.lower().endswith(ext) for ext in _ASSET_EXTENSIONS):
            continue
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != expected_depth or parts[0] != target_root:
            continue
        seen.add(candidate)
        version_roots.append(candidate)

    return version_roots


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


