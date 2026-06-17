

"""External HTTP web-search provider adapters for seed discovery.

Each adapter turns a constructed query into a same-domain seed-URL set for one external
search backend (TinyFish, SearXNG, Brave, DuckDuckGo). They share the JSON fetch/normalize
helpers defined alongside the parsing chunk and are dispatched by
``_external_web_search_seed_urls`` in the core chunk. Tavily lives next to the shared
helpers it is coupled to. DuckDuckGo is the only key-free backend: it scrapes the HTML
endpoint, so it doubles as the ``auto`` fallback when no search API key is configured.
"""

def _tinyfish_web_search_seed_urls(
    start_url: str,
    start_parsed: ParseResult,
    max_candidates: int,
) -> set[str]:
    api_key = os.environ.get("TINYFISH_API_KEY", "").strip()
    if not api_key:
        return set()

    query = _build_web_search_query(start_url, start_parsed)
    params = urlencode({"query": query})
    request = Request(
        f"{TINYFISH_SEARCH_API_URL}?{params}",
        headers={
            "X-API-Key": api_key,
            "Accept": JSON_CONTENT_TYPE,
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="GET",
    )
    payload = _load_json_response(request)
    if payload is None:
        return set()
    extracted = _extract_urls_from_json(payload)
    return _normalize_search_urls(extracted, start_parsed, max_candidates)


def _searxng_web_search_seed_urls(query: str, start_parsed: ParseResult, max_candidates: int) -> set[str]:
    base_url = os.environ.get("SEARXNG_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return set()

    endpoint = (
        base_url
        if base_url.lower().endswith(SEARXNG_SEARCH_URL_SUFFIX)
        else f"{base_url}{SEARXNG_SEARCH_URL_SUFFIX}"
    )
    params = urlencode({"q": query, "format": "json"})
    request = Request(
        f"{endpoint}?{params}",
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": JSON_CONTENT_TYPE},
        method="GET",
    )
    payload = _load_json_response(request)
    if payload is None:
        return set()
    extracted = _extract_urls_from_json(payload)
    return _normalize_search_urls(extracted, start_parsed, max_candidates)


def _duckduckgo_web_search_seed_urls(query: str, start_parsed: ParseResult, max_candidates: int) -> set[str]:
    params = urlencode({"q": query})
    request = Request(
        f"{DUCKDUCKGO_SEARCH_URL}?{params}",
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=WEB_SEARCH_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return set()
    extracted = _extract_urls_from_ddg_html(body)
    return _normalize_search_urls(extracted, start_parsed, max_candidates)


def _extract_urls_from_ddg_html(body: str) -> list[str]:
    """Pull result URLs out of the DuckDuckGo HTML endpoint.

    Result anchors usually point at a ``/l/?uddg=<urlencoded target>`` redirect; older
    layouts link the target directly. Everything else (assets, internal links) is dropped.
    """
    urls: list[str] = []
    for match in re.finditer(r'href="([^"]+)"', body):
        href = unescape(match.group(1))
        if "uddg=" in href:
            for target in parse_qs(urlparse(href).query).get("uddg", []):
                urls.append(target)
        elif href.startswith(("http://", "https://")) and "duckduckgo.com" not in href:
            urls.append(href)
    return urls


def _brave_web_search_seed_urls(query: str, start_parsed: ParseResult, max_candidates: int) -> set[str]:
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        return set()

    params = urlencode({"q": query, "count": max(5, max_candidates)})
    request = Request(
        f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={
            "Accept": JSON_CONTENT_TYPE,
            "User-Agent": DEFAULT_USER_AGENT,
            "X-Subscription-Token": api_key,
        },
        method="GET",
    )
    payload = _load_json_response(request)
    if payload is None:
        return set()
    extracted = _extract_urls_from_json(payload)
    return _normalize_search_urls(extracted, start_parsed, max_candidates)
