

"""LLM URL parsing and candidate ranking.

Extracts text from provider responses, parses URL suggestions, ranks candidates by
documentation-likeness, and filters links before live probing.
"""

def _extract_message_content_from_dict(response: object) -> str:
    if not isinstance(response, dict):
        return ""

    message = response.get("message") or {}
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content

    content = response.get("content")
    return content if isinstance(content, str) else ""


def _extract_message_content_from_object(response: object) -> str:
    message_obj = getattr(response, "message", None)
    if message_obj is not None:
        content_attr = getattr(message_obj, "content", None)
        if isinstance(content_attr, str):
            return content_attr
        if isinstance(message_obj, dict):
            content = message_obj.get("content")
            if isinstance(content, str):
                return content

    direct_content = getattr(response, "content", None)
    return direct_content if isinstance(direct_content, str) else ""


def _parse_urls_from_llm(text: str) -> set[str]:
    text = text.strip()

    # First try strict JSON array parsing.
    if text.startswith("[") and text.endswith("]"):
        try:
            payload = json.loads(text)
            if isinstance(payload, list):
                return {
                    _normalize_url(str(item).strip())
                    for item in payload
                    if isinstance(item, str)
                }
        except Exception:
            pass

    # Fallback: extract URLs from free-form content.
    matches = re.findall(r"https?://[^\s\]\)\"']+", text)
    return {_normalize_url(match) for match in matches}


def _rank_candidates(candidates: Iterable[str], start_parsed: ParseResult, start_url: str) -> list[str]:
    ranked = sorted(
        (candidate for candidate in candidates if candidate and candidate != start_url),
        key=lambda candidate: _candidate_sort_key(candidate, start_parsed),
    )
    return ranked


def _candidate_sort_key(candidate: str, start_parsed: ParseResult) -> tuple[int, int, str]:
    parsed = urlparse(candidate)
    path = parsed.path.lower()
    start_path = (start_parsed.path.rstrip("/") or "/").lower()

    score = 0
    if start_path != "/" and path.startswith(start_path + "/"):
        score += 6
    if any(hint in path for hint in DOC_PATH_HINTS):
        score += 4
    if path.endswith(".html"):
        score += 2
    if path.endswith("/"):
        score += 1
    if any(path.endswith(ext) for ext in BLOCKED_SEED_FILE_EXTENSIONS):
        score -= 5

    # Primary sort is by score (descending), then prefer shorter, cleaner paths.
    return (-score, len(path), candidate)


def _is_viable_seed_link(link: str, start_parsed) -> bool:
    parsed = urlparse(link)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if parsed.netloc.lower() != start_parsed.netloc.lower():
        return False

    path = parsed.path.lower()
    if not path or path == "/":
        return False
    if any(path.endswith(ext) for ext in BLOCKED_SEED_FILE_EXTENSIONS):
        return False

    start_path = (start_parsed.path.rstrip("/") or "/").lower()
    if start_path != "/" and path.startswith(start_path + "/"):
        return True
    return any(hint in path for hint in DOC_PATH_HINTS)
