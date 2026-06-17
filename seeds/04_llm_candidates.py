


"""LLM-assisted seed candidate generation.

Builds the page-context prompt for a configured LLM, optionally augments it with web
search, parses same-domain URL suggestions, and reports diagnostics for the caller.
"""

def _llm_seed_candidates(
    start_url: str,
    start_parsed: ParseResult,
    page_links: list[str],
    page_context: PageSeedContext,
    deterministic_candidates: list[str],
    llm_model: str,
    llm_provider: str,
    max_candidates: int,
    use_web_search: bool,
) -> tuple[set[str], str]:
    provider = _normalize_llm_provider(llm_provider)
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if provider == "cloud" and not api_key:
        return set(), "missing-api-key"
    if provider == "gemini" and not os.environ.get("GEMINI_API_KEY", "").strip():
        return set(), "missing-gemini-api-key"

    client = None
    if provider in {"cloud", "local"}:
        try:
            ollama_module = importlib.import_module("ollama")
            client_cls = getattr(ollama_module, "Client", None)
            if client_cls is None:
                return set(), "ollama-client-missing"
        except Exception:
            return set(), "ollama-package-missing"
        client = _make_ollama_client(client_cls, provider, api_key)

    extraction_prompt_template = (
        "Extract all absolute URLs from the following analysis and return ONLY a JSON array of strings.\n"
        "Rules:\n"
        f"- Same domain only: {start_parsed.netloc}\n"
        "- Exclude images/css/js/assets/download pages.\n"
        f"- Cap output to at most {max(1, max_candidates)} URLs.\n"
        "- Output JSON only, no prose.\n\n"
        "Analysis:\n{analysis_text}"
    )

    progress = {"phase": "contacting web search"}

    def _status() -> str:
        return f"{progress['phase']} [{llm_model}]"

    try:
        with _HeartbeatLogger(label="Ollama seed analysis", status_fn=_status):
            web_search_urls, native_web_search = _llm_optional_web_search(
                use_web_search=use_web_search,
                llm_provider=provider,
                api_key=api_key,
                start_url=start_url,
                start_parsed=start_parsed,
                max_candidates=max_candidates,
            )
            _announce_web_search_hits(web_search_urls, max_candidates)
            progress["phase"] = (
                f"analyzing the page with the model - {len(web_search_urls)} web seed(s) already secured"
            )

            analysis_prompt = _build_llm_analysis_prompt(
                start_url=start_url,
                start_parsed=start_parsed,
                page_links=page_links,
                page_context=page_context,
                deterministic_candidates=deterministic_candidates,
                max_candidates=max_candidates,
                web_search_candidates=sorted(web_search_urls),
            )

            analysis_text = _llm_generate_analysis_text(
                client=client,
                llm_provider=provider,
                llm_model=llm_model,
                analysis_prompt=analysis_prompt,
                use_web_search=native_web_search,
            )
            if not analysis_text:
                if web_search_urls:
                    return set(web_search_urls), "web-search-only-llm-timeout"
                return set(), "llm-analysis-timeout-or-empty"

            progress["phase"] = "extracting seed URLs from the model's analysis"
            extraction_text = _llm_extract_seed_text(
                client=client,
                llm_provider=provider,
                llm_model=llm_model,
                extraction_prompt=extraction_prompt_template.format(analysis_text=analysis_text),
                use_web_search=native_web_search,
            )
            if not extraction_text:
                if web_search_urls:
                    return set(web_search_urls), "web-search-only-llm-timeout"
                return set(), "llm-extraction-timeout-or-empty"

            suggested_urls = _parse_urls_from_llm(extraction_text)
            suggested_urls.update(web_search_urls)
    except Exception:
        return set(), "ollama-request-failed"

    normalized = {
        _normalize_url(url)
        for url in suggested_urls
        if _normalize_url(url)
    }
    if not normalized:
        return set(), "no-viable-llm-seeds"
    return normalized, "ok-web" if use_web_search else "ok"


def _announce_web_search_hits(web_search_urls: set[str], max_candidates: int) -> None:
    """Stream web-search hits to the user immediately, before the slow model call."""
    if not web_search_urls:
        return
    print(
        f"Seed discovery: web search found {len(web_search_urls)} candidate URL(s):",
        file=sys.stderr,
    )
    for hit in sorted(web_search_urls)[: max(1, max_candidates)]:
        print(f"    + {hit}", file=sys.stderr)
