

"""Seed LLM provider setup and response extraction.

Normalizes provider names, constructs Ollama clients, calls chat APIs with a timeout, and
extracts candidate text while preserving optional web-search request shapes.
"""

def _llm_optional_web_search(
    use_web_search: bool,
    llm_provider: str,
    api_key: str,
    start_url: str,
    start_parsed: ParseResult,
    max_candidates: int,
) -> tuple[set[str], bool]:
    if not use_web_search:
        return set(), False
    if llm_provider == "gemini":
        return set(), True

    requested = (os.environ.get("DOC_INGESTOR_WEB_SEARCH_PROVIDER") or DEFAULT_WEB_SEARCH_PROVIDER).strip().lower()
    if requested == "ollama":
        if llm_provider != "cloud" or not api_key:
            return set(), False
        return _ollama_web_search_seed_urls(
            api_key=api_key,
            start_url=start_url,
            start_parsed=start_parsed,
            max_candidates=max_candidates,
        ), True

    external_urls = _external_web_search_seed_urls(
        start_url=start_url,
        start_parsed=start_parsed,
        max_candidates=max_candidates,
    )
    if external_urls:
        return external_urls, False

    if llm_provider != "cloud" or not api_key:
        return set(), False
    return _ollama_web_search_seed_urls(
        api_key=api_key,
        start_url=start_url,
        start_parsed=start_parsed,
        max_candidates=max_candidates,
    ), True


def _normalize_llm_provider(llm_provider: str) -> str:
    return llm_provider if llm_provider in {"cloud", "local", "gemini"} else DEFAULT_OLLAMA_PROVIDER


def _make_ollama_client(client_cls: object, llm_provider: str, api_key: str) -> object:
    if llm_provider == "local":
        return client_cls(host=os.environ.get("OLLAMA_HOST", LOCAL_OLLAMA_HOST))
    return client_cls(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"},
    )


def _llm_generate_analysis_text(
    client: object | None,
    llm_provider: str,
    llm_model: str,
    analysis_prompt: str,
    use_web_search: bool,
) -> str:
    if llm_provider == "gemini":
        return _gemini_generate_text(
            model=llm_model,
            system=ANALYSIS_SYSTEM_PROMPT,
            user=analysis_prompt,
            use_web_search=use_web_search,
        )
    kwargs = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": analysis_prompt},
        ],
        "stream": False,
    }
    if use_web_search:
        kwargs["options"] = {"web_search": True}
    return _chat_with_timeout(client, kwargs)


def _llm_extract_seed_text(
    client: object | None,
    llm_provider: str,
    llm_model: str,
    extraction_prompt: str,
    use_web_search: bool,
) -> str:
    if llm_provider == "gemini":
        return _gemini_generate_text(
            model=llm_model,
            system="You extract URLs and return strict JSON.",
            user=extraction_prompt,
            use_web_search=use_web_search,
        )
    kwargs = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": "You extract URLs and return strict JSON."},
            {"role": "user", "content": extraction_prompt},
        ],
        "stream": False,
    }
    if use_web_search:
        kwargs["options"] = {"web_search": True}
    return _chat_with_timeout(client, kwargs)


def _chat_with_timeout(client: object, kwargs: dict[str, object]) -> str:
    timeout_seconds = _resolve_llm_timeout_seconds()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.chat, **kwargs)
        try:
            response = future.result(timeout=timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            print(
                f"Seed discovery: LLM call timed out after {int(timeout_seconds)}s; falling back to heuristic seeds.",
                file=sys.stderr,
            )
            return ""
        except Exception:
            return ""
    return _extract_message_content(response)
