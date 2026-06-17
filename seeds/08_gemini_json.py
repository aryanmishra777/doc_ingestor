

"""Gemini seed generation and structured URL parsing.

Builds Gemini requests, extracts response text, resolves LLM timeouts, pulls URLs from JSON
payloads, and applies same-domain filtering.
"""

def _gemini_generate_text(
    model: str,
    system: str,
    user: str,
    use_web_search: bool,
) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""

    payload: dict[str, object] = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
    }
    if use_web_search:
        payload["tools"] = [{"google_search": {}}]

    try:
        response = requests.post(
            f"{GEMINI_API_BASE_URL}/models/{model}:generateContent",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_resolve_llm_timeout_seconds(),
        )
        response.raise_for_status()
    except Exception:
        return ""

    return _extract_gemini_text(response.json())


def _extract_gemini_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return ""
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        texts = [part.get("text", "") for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)]
        joined = "".join(texts).strip()
        if joined:
            return joined
    return ""


def _resolve_llm_timeout_seconds() -> float | None:
    """Resolve the seed LLM timeout. ``None`` means wait with no cap.

    ``off``/``none``/``disabled``/``never``/``unlimited`` (or a non-positive number)
    disable the timeout entirely, so a slow local model can finish if you'd rather
    watch the live progress screen than fall back early.
    """
    raw = os.environ.get("DOC_INGESTOR_LLM_TIMEOUT_SECONDS", "").strip().lower()
    if not raw:
        return DEFAULT_LLM_TIMEOUT_SECONDS
    if raw in {"off", "none", "disabled", "never", "unlimited"}:
        return None
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_LLM_TIMEOUT_SECONDS
    return None if value <= 0 else max(5.0, value)


def _extract_urls_from_json(payload: object) -> set[str]:
    urls: set[str] = set()

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.lower() in {"url", "link", "href"} and isinstance(value, str):
                urls.add(value)
            urls.update(_extract_urls_from_json(value))
        return urls

    if isinstance(payload, list):
        for item in payload:
            urls.update(_extract_urls_from_json(item))
        return urls

    if isinstance(payload, str):
        urls.update(re.findall(r"https?://[^\s\]\)\"']+", payload))
    return urls


def _same_domain(url: str, start_parsed: ParseResult) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.lower() == start_parsed.netloc.lower()
