

"""Web-search provider routing for seed discovery.

Routes seed-search requests through Ollama cloud search or a configured external provider,
and implements query construction plus provider resolution. The external HTTP adapters
themselves (TinyFish/SearXNG/Brave) live in the companion ``web_search_adapters`` chunk.
"""

def _ollama_web_search_seed_urls(
    api_key: str,
    start_url: str,
    start_parsed: ParseResult,
    max_candidates: int,
) -> set[str]:
    query = _build_web_search_query(start_url, start_parsed)
    body = json.dumps({"query": query, "max_results": max(5, max_candidates)}).encode("utf-8")
    request = Request(
        "https://ollama.com/api/web_search",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": JSON_CONTENT_TYPE,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=WEB_SEARCH_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return set()

    try:
        payload = json.loads(raw)
    except Exception:
        return set()

    extracted = _extract_urls_from_json(payload)
    return {
        normalized
        for url in extracted
        for normalized in [_normalize_url(url)]
        if normalized and _same_domain(normalized, start_parsed)
    }


def _external_web_search_seed_urls(
    start_url: str,
    start_parsed: ParseResult,
    max_candidates: int,
) -> set[str]:
    provider = _resolve_external_web_search_provider()
    query = _build_web_search_query(start_url, start_parsed)
    if provider == "tinyfish":
        return _tinyfish_web_search_seed_urls(start_url, start_parsed, max_candidates)
    if provider == "searxng":
        return _searxng_web_search_seed_urls(query, start_parsed, max_candidates)
    if provider == "brave":
        return _brave_web_search_seed_urls(query, start_parsed, max_candidates)
    if provider == "tavily":
        return _tavily_web_search_seed_urls(query, start_parsed, max_candidates)
    if provider == "duckduckgo":
        return _duckduckgo_web_search_seed_urls(query, start_parsed, max_candidates)
    return set()


def _build_web_search_query(start_url: str, start_parsed: ParseResult) -> str:
    return (
        f"site:{start_parsed.netloc} documentation seed URLs "
        f"reference api index module namespace for {start_url}"
    )


def _resolve_external_web_search_provider() -> str | None:
    requested = (os.environ.get("DOC_INGESTOR_WEB_SEARCH_PROVIDER") or DEFAULT_WEB_SEARCH_PROVIDER).strip().lower()
    if requested in {"disabled", "none", "off"}:
        return None
    if requested == "ddg":
        return "duckduckgo"
    if requested in {"tinyfish", "searxng", "brave", "tavily", "duckduckgo"}:
        return requested

    if os.environ.get("TINYFISH_API_KEY", "").strip():
        return "tinyfish"
    if os.environ.get("SEARXNG_BASE_URL", "").strip():
        return "searxng"
    if os.environ.get("BRAVE_SEARCH_API_KEY", "").strip():
        return "brave"
    if os.environ.get("TAVILY_API_KEY", "").strip():
        return "tavily"
    # DuckDuckGo needs no API key, so `auto` always has a working provider.
    return "duckduckgo"
