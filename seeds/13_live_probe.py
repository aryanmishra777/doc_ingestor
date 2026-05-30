

"""Live seed probing and URL normalization.

Verifies ranked candidate seeds with lightweight HEAD/GET probes, checks content type and
final URL shape, and normalizes accepted URLs for crawl entry points.
"""

def _select_live_candidates(
    ranked_candidates: list[str],
    start_parsed: ParseResult,
    max_count: int,
    allow_unverified_fallback: bool = True,
) -> list[str]:
    if max_count <= 0:
        return []

    from concurrent.futures import ThreadPoolExecutor, as_completed

    probe_budget = min(MAX_PROBE_CANDIDATES, len(ranked_candidates))
    to_probe = ranked_candidates[:probe_budget]

    # Probe all candidates concurrently; preserve ranked order in results.
    results: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=min(probe_budget, 10)) as executor:
        future_to_url = {
            executor.submit(_is_live_doc_candidate, url, start_parsed): url
            for url in to_probe
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = False

    selected = [url for url in to_probe if results.get(url)][:max_count]

    if selected:
        return selected

    if allow_unverified_fallback:
        # Fallback for restrictive sites that block HEAD/GET probing.
        return ranked_candidates[:max_count]
    return []


def _is_live_doc_candidate(candidate: str, start_parsed: ParseResult) -> bool:
    request = Request(
        candidate,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5",
        },
        method="HEAD",
    )

    try:
        with urlopen(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
            return _response_looks_like_document(response.getcode(), response.geturl(), response.headers.get("Content-Type", ""), start_parsed)
    except HTTPError as exc:
        if exc.code == 405:
            return _probe_with_get(candidate, start_parsed)
        if exc.code >= 400:
            return False
        return _response_looks_like_document(exc.code, candidate, exc.headers.get("Content-Type", ""), start_parsed)
    except URLError:
        return False
    except TimeoutError:
        return False
    except Exception:
        return False


def _probe_with_get(candidate: str, start_parsed: ParseResult) -> bool:
    request = Request(
        candidate,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
            return _response_looks_like_document(response.getcode(), response.geturl(), response.headers.get("Content-Type", ""), start_parsed)
    except Exception:
        return False


def _response_looks_like_document(status: int | None, final_url: str, content_type: str, start_parsed: ParseResult) -> bool:
    if status is not None and status >= 400:
        return False

    normalized_final_url = _normalize_url(final_url)
    if not normalized_final_url:
        return False

    final_parsed = urlparse(normalized_final_url)
    if final_parsed.netloc.lower() != start_parsed.netloc.lower():
        return False

    lowered_type = (content_type or "").lower()
    if not lowered_type:
        return True
    if "text/html" in lowered_type or "application/xhtml+xml" in lowered_type or "text/plain" in lowered_type:
        return True

    return False


def _parent_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "/"
    if len(parts) == 1:
        return "/"
    return "/" + "/".join(parts[:-1]) + "/"


def _normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))
