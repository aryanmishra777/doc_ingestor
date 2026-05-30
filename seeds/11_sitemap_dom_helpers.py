

"""Robots/sitemap crawling and DOM safety helpers.

Discovers sitemap references, consumes sitemap documents, provides defensive DOM helpers,
and normalizes text/message content used by later ranking steps.
"""

def _discover_sitemap_urls_from_robots(
    robots_url: str,
    default_sitemap_url: str,
    start_parsed: ParseResult,
) -> set[str]:
    sitemap_urls: set[str] = {default_sitemap_url}
    text = _fetch_text_url(robots_url, ROBOTS_TIMEOUT_SECONDS)
    if not text:
        return sitemap_urls

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.lower().startswith("sitemap:"):
            continue
        candidate = _normalize_url(line.split(":", 1)[1].strip())
        if candidate and _same_domain(candidate, start_parsed):
            sitemap_urls.add(candidate)
    return sitemap_urls


def _collect_seed_urls_from_sitemaps(start_parsed: ParseResult, sitemap_urls: set[str]) -> set[str]:
    results: set[str] = set()
    visited_sitemaps: set[str] = set()
    queue = list(sitemap_urls)

    while queue and len(visited_sitemaps) < MAX_SITEMAP_FILES and len(results) < MAX_SITEMAP_URLS:
        sitemap = queue.pop(0)
        if sitemap in visited_sitemaps:
            continue
        visited_sitemaps.add(sitemap)

        body = _fetch_text_url(sitemap, SITEMAP_TIMEOUT_SECONDS)
        if not body:
            continue

        _consume_sitemap_locs(
            body=body,
            start_parsed=start_parsed,
            results=results,
            visited_sitemaps=visited_sitemaps,
            queue=queue,
        )
    return results


def _consume_sitemap_locs(
    body: str,
    start_parsed: ParseResult,
    results: set[str],
    visited_sitemaps: set[str],
    queue: list[str],
) -> None:
    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", body, flags=re.IGNORECASE)
    for loc in locs:
        candidate = _normalize_url(unescape(loc.strip()))
        if not candidate or not _same_domain(candidate, start_parsed):
            continue
        if candidate.endswith(".xml") and "sitemap" in candidate.lower():
            if candidate not in visited_sitemaps:
                queue.append(candidate)
            continue
        if _is_viable_seed_link(candidate, start_parsed):
            results.add(candidate)
        if len(results) >= MAX_SITEMAP_URLS:
            break


def _fetch_text_url(url: str, timeout_seconds: float) -> str:
    try:
        request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT}, method="GET")
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _safe_element_text(element: object) -> str:
    try:
        return (element.inner_text(timeout=800) or "").strip().lower()
    except Exception:
        return ""


def _safe_element_href(element: object) -> str:
    try:
        return _normalize_url((element.get_attribute("href") or "").strip())
    except Exception:
        return ""


def _click_and_collect(page: object, element: object, start_parsed: ParseResult, discovered: set[str]) -> bool:
    try:
        element.scroll_into_view_if_needed(timeout=1_000)
        element.click(timeout=1_500)
        page.wait_for_timeout(400)
        current_url = _normalize_url(page.url)
        if current_url and _same_domain(current_url, start_parsed):
            discovered.add(current_url)
        discovered.update(_collect_internal_anchors_from_dom(page, start_parsed))
        return True
    except Exception:
        return False


def _clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    normalized = " ".join(unescape(without_tags).split())
    return normalized.strip()


def _looks_like_non_doc_asset(url: str) -> bool:
    lowered = urlparse(url).path.lower()
    return any(lowered.endswith(ext) for ext in NON_DOC_ASSET_EXTENSIONS)


def _extract_message_content(response: object) -> str:
    dict_content = _extract_message_content_from_dict(response)
    if dict_content:
        return dict_content

    object_content = _extract_message_content_from_object(response)
    if object_content:
        return object_content

    return ""
