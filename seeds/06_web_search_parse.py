

"""Web-search response parsing and LLM prompt assembly.

Implements the Tavily adapter, JSON response loading, same-domain URL normalization, and
the compact analysis prompt used for seed-suggestion models.
"""

def _tavily_web_search_seed_urls(query: str, start_parsed: ParseResult, max_candidates: int) -> set[str]:
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return set()

    body = json.dumps(
        {
            "api_key": api_key,
            "query": query,
            "max_results": max(5, max_candidates),
            "search_depth": "basic",
            "include_raw_content": False,
        }
    ).encode("utf-8")
    request = Request(
        "https://api.tavily.com/search",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="POST",
    )
    payload = _load_json_response(request)
    if payload is None:
        return set()
    extracted = _extract_urls_from_json(payload)
    return _normalize_search_urls(extracted, start_parsed, max_candidates)


def _load_json_response(request: Request) -> object | None:
    try:
        with urlopen(request, timeout=WEB_SEARCH_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    try:
        return json.loads(raw)
    except Exception:
        return None


def _normalize_search_urls(urls: Iterable[str], start_parsed: ParseResult, max_candidates: int) -> set[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = _normalize_url(url)
        if not normalized or not _same_domain(normalized, start_parsed):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
        if len(ordered) >= max(1, max_candidates):
            break
    return set(ordered)


def _build_llm_analysis_prompt(
    start_url: str,
    start_parsed: ParseResult,
    page_links: list[str],
    page_context: PageSeedContext,
    deterministic_candidates: list[str],
    max_candidates: int,
    web_search_candidates: list[str] | None = None,
) -> str:
    links_excerpt = _excerpt_lines(page_links, MAX_LLM_CONTEXT_LINKS)
    headings_excerpt = _excerpt_lines(page_context.headings, MAX_CONTEXT_HEADINGS)
    nav_excerpt = _excerpt_lines(page_context.nav_labels, MAX_CONTEXT_NAV_LABELS)
    scripts_excerpt = _excerpt_lines(page_context.script_urls, MAX_CONTEXT_SCRIPT_URLS)
    iframe_excerpt = _excerpt_lines(page_context.iframe_urls, MAX_CONTEXT_SCRIPT_URLS)
    interaction_excerpt = _excerpt_lines(page_context.interaction_urls, MAX_LLM_CONTEXT_LINKS)
    network_excerpt = _excerpt_lines(page_context.network_urls, MAX_LLM_CONTEXT_LINKS)
    deterministic_excerpt = _excerpt_lines(deterministic_candidates, MAX_LLM_CONTEXT_LINKS)
    web_search_excerpt = _excerpt_lines(web_search_candidates or [], MAX_LLM_CONTEXT_LINKS)

    return (
        "Context:\n"
        "- We built a website-agnostic documentation crawler.\n"
        "- Goal: choose seed URLs that lead to dense documentation clusters.\n"
        "- We will recursively crawl from your seed list and deduplicate results.\n\n"
        f"Target documentation URL: {start_url}\n"
        f"Final rendered URL (after redirects): {page_context.final_url or start_url}\n"
        f"Allowed domain: {start_parsed.netloc}\n"
        f"Maximum number of seed URLs desired: {max(1, max_candidates)}\n\n"
        f"Rendered page title: {page_context.title or NO_CONTEXT_VALUE}\n\n"
        "Observed headings from rendered page:\n"
        f"{headings_excerpt}\n\n"
        "Observed navigation labels or doc-like anchor labels:\n"
        f"{nav_excerpt}\n\n"
        "Observed links from the start page:\n"
        f"{links_excerpt}\n\n"
        "URLs discovered after lightweight interactions:\n"
        f"{interaction_excerpt}\n\n"
        "Same-domain URLs observed through network responses:\n"
        f"{network_excerpt}\n\n"
        "Script source URLs on the rendered page:\n"
        f"{scripts_excerpt}\n\n"
        "Iframe/frame source URLs on the rendered page:\n"
        f"{iframe_excerpt}\n\n"
        "Deterministic candidate URLs already found (heuristics + robots/sitemap):\n"
        f"{deterministic_excerpt}\n\n"
        "URLs found through web search:\n"
        f"{web_search_excerpt}\n\n"
        "Task:\n"
        "1) Analyze the likely documentation structure for this URL.\n"
        "2) Propose high-value seed URLs (top-level indexes/namespaces/clusters).\n"
        "3) Keep every URL absolute and on the allowed domain.\n"
        "4) Prefer pages/directories that maximize coverage quickly."
    )


def _excerpt_lines(values: list[str], limit: int) -> str:
    return "\n".join(values[:limit]) or NO_CONTEXT_VALUE
