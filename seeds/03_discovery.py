

"""Seed-discovery orchestration and heuristic candidates.

Combines heuristic URL guesses, robots/sitemap discoveries, optional browser context, and
optional LLM suggestions into ranked candidate seed URLs with diagnostics.
"""

def discover_seed_urls_with_diagnostics(
    start_url: str,
    max_seed_urls: int = 8,
    use_llm: bool = False,
    llm_model: str = DEFAULT_LLM_SEED_MODEL,
    llm_provider: str = DEFAULT_OLLAMA_PROVIDER,
    use_web_search: bool = False,
) -> tuple[list[str], SeedDiscoveryDiagnostics]:
    normalized_start = _normalize_url(start_url)
    if not normalized_start:
        return [start_url], SeedDiscoveryDiagnostics(
            llm_requested=use_llm,
            llm_attempted=False,
            llm_used=False,
            llm_reason="invalid-start-url",
            llm_candidate_count=0,
        )

    start_parsed = urlparse(normalized_start)
    page_context = _build_page_seed_context(normalized_start, start_parsed)
    linked = set(page_context.internal_links)
    linked.update(page_context.interaction_urls)
    linked.update(page_context.network_urls)
    linked.update(page_context.iframe_urls)
    linked = {
        link
        for link in linked
        if _is_viable_seed_link(link, start_parsed)
    }
    candidates = set(_heuristic_candidates(start_parsed))
    candidates.update(linked)
    candidates.update(_robots_and_sitemap_candidates(start_parsed))
    diagnostics = SeedDiscoveryDiagnostics(
        llm_requested=use_llm,
        llm_attempted=False,
        llm_used=False,
        llm_reason="not-requested",
        llm_candidate_count=0,
    )

    if use_llm:
        llm_candidates, llm_reason = _llm_seed_candidates(
            start_url=normalized_start,
            start_parsed=start_parsed,
            page_links=sorted(linked),
            page_context=page_context,
            deterministic_candidates=sorted(candidates),
            llm_model=llm_model,
            llm_provider=llm_provider,
            max_candidates=max_seed_urls,
            use_web_search=use_web_search,
        )
        diagnostics = SeedDiscoveryDiagnostics(
            llm_requested=True,
            llm_attempted=True,
            llm_used=bool(llm_candidates),
            llm_reason=llm_reason,
            llm_candidate_count=len(llm_candidates),
        )

        if llm_candidates:
            llm_ranked = sorted(
                candidate
                for candidate in llm_candidates
                if candidate and candidate != normalized_start
            )
            llm_selected = _select_live_candidates(
                llm_ranked,
                start_parsed,
                max_count=max(0, max_seed_urls - 1),
                allow_unverified_fallback=False,
            )
            return [normalized_start, *llm_selected], diagnostics

    ranked = _rank_candidates(candidates, start_parsed, start_url=normalized_start)
    selected = _select_live_candidates(ranked, start_parsed, max_count=max(0, max_seed_urls - 1))

    return [normalized_start, *selected], diagnostics


def _heuristic_candidates(start_parsed: ParseResult) -> set[str]:
    base = f"{start_parsed.scheme}://{start_parsed.netloc}"
    start_path = start_parsed.path or "/"

    path_options = {
        start_path,
        start_path.rstrip("/") + "/",
        _parent_path(start_path),
    }

    candidates: set[str] = set()
    for base_path in path_options:
        for suffix in COMMON_SEED_SUFFIXES:
            candidate = _normalize_url(urljoin(base, urljoin(base_path, suffix)))
            if candidate:
                candidates.add(candidate)
    return candidates
