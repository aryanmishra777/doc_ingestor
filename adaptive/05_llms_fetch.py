

# ---------------------------------------------------------------------------
# Deterministic handler: llms.txt / llms-full.txt
# ---------------------------------------------------------------------------

"""llms.txt fetching and richer-source selection.

Handles the adaptive llms.txt phase: fetch the detected source, analyze whether a linked
``llms-full.txt`` is richer, avoid same-file anchors, and pass the selected Markdown on
to the parser.
"""

def _handle_fetch_llms_txt(state: AgentState, log: Callable[[str], None]) -> None:
    content = state.detection.prefetched_content or ""
    if not content or _should_refetch_llms_txt(state.detection.url, content):
        r = _http_get(state.detection.url, read_limit=LLMS_TXT_READ_LIMIT)
        content = r["body"] if r and r["status"] == 200 else ""

    if not content:
        log("Adaptive: llms.txt empty or unreadable, falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return

    # Single-pass: count prose words and collect link URLs simultaneously.
    prose_word_count, link_urls = _analyze_llms_txt(content, state.detection.url)

    preferred_full = _fetch_preferred_llms_full(
        content,
        current_url=state.detection.url,
        current_word_count=prose_word_count,
        log=log,
    )
    if preferred_full is not None:
        state.detection.url = preferred_full[0]
        state.detection.prefetched_content = preferred_full[1]
        content = preferred_full[1]
        prose_word_count, link_urls = _analyze_llms_txt(content, state.detection.url)

    is_full_content = prose_word_count > 300 and len(link_urls) < prose_word_count // 10

    if is_full_content:
        log(f"Adaptive: llms.txt contains full content ({prose_word_count} words), parsing into records...")
        state.doc_records = _parse_llms_full_content(content, state.detection.url)
        log(f"Adaptive: parsed {len(state.doc_records)} records from llms.txt")
    else:
        log(f"Adaptive: llms.txt is a link index ({len(link_urls)} URLs), fetching pages...")
        same_domain = urlparse(state.target_url).netloc.lower()
        urls = [u for u in link_urls if urlparse(u).netloc.lower() == same_domain] or link_urls
        workers = state.crawler_kwargs.get("max_workers", 4)
        include_sparse = state.crawler_kwargs.get("include_sparse_pages", False)
        state.doc_records = _fetch_url_list(urls, max_workers=workers, log=log, include_sparse_pages=include_sparse)
        log(f"Adaptive: fetched {len(state.doc_records)} records from llms.txt links")

    state.phase = CrawlerPhase.EVALUATE_QUALITY


def _should_refetch_llms_txt(url: str, content: str) -> bool:
    parsed = urlparse(url)
    if parsed.path.lower().endswith("llms-full.txt"):
        return True
    return len(content.encode("utf-8")) >= 60 * 1024


def _analyze_llms_txt(content: str, source_url: str) -> tuple[int, list[str]]:
    link_urls: list[str] = []
    prose_word_count = 0
    last = 0
    for m in _iter_markdown_links(content):
        prose_word_count += len(content[last : m.start()].split())
        href = m.group(2).strip()
        if href and not href.startswith("#"):
            link_urls.append(urljoin(source_url, href))
        last = m.end()
    prose_word_count += len(content[last:].split())
    return prose_word_count, link_urls


def _iter_markdown_links(content: str) -> Any:
    return re.finditer(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", content)


def _fetch_preferred_llms_full(
    content: str,
    *,
    current_url: str,
    current_word_count: int,
    log: Callable[[str], None],
) -> tuple[str, str] | None:
    candidates: list[str] = []
    current = urlparse(current_url)
    current_normalized = current._replace(fragment="").geturl().rstrip("/")

    for m in _iter_markdown_links(content):
        label = m.group(1).lower()
        href = m.group(2).strip()
        candidate = urljoin(current_url, href)
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.lower() != current.netloc.lower():
            continue
        candidate_normalized = parsed._replace(fragment="").geturl().rstrip("/")
        if candidate_normalized == current_normalized:
            continue
        path = parsed.path.lower()
        if path.endswith("/llms-full.txt") or path.endswith("llms-full.txt") or (
            "full" in label and path.endswith("llms.txt")
        ):
            candidates.append(candidate)

    for candidate in dict.fromkeys(candidates):
        log(f"Adaptive: discovered richer llms-full source at {candidate}, fetching...")
        r = _http_get(candidate, read_limit=LLMS_TXT_READ_LIMIT)
        body = r["body"] if r and r["status"] == 200 else ""
        if not body:
            continue
        candidate_word_count, _ = _analyze_llms_txt(body, candidate)
        if candidate_word_count > max(current_word_count, 300):
            log(
                "Adaptive: using richer llms-full source "
                f"({candidate_word_count} words vs {current_word_count})"
            )
            return candidate, body

    return None
