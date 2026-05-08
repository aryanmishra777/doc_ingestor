from __future__ import annotations

import json
import importlib
import os
import re
import sys
import threading
import time
from html import unescape
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

try:
    from .extraction import extract_page
except ImportError:
    from extraction import extract_page

DOC_PATH_HINTS = (
    "docs",
    "doc",
    "documentation",
    "reference",
    "api",
    "guide",
    "manual",
    "tutorial",
    "learn",
    "find",
    "search",
    "index",
)

COMMON_SEED_SUFFIXES = (
    "index.html",
    "reference/",
    "api/",
    "docs/",
    "documentation/",
    "guide/",
    "manual/",
    "tutorial/",
    "find/",
    "search/",
    "all.html",
    "modules.html",
)

MAX_PROBE_CANDIDATES = 20
PROBE_TIMEOUT_SECONDS = 4.0
DEFAULT_LLM_SEED_MODEL = "gemma4:31b-cloud"
MAX_LLM_CONTEXT_LINKS = 60
WEB_SEARCH_TIMEOUT_SECONDS = 8.0
ROBOTS_TIMEOUT_SECONDS = 5.0
SITEMAP_TIMEOUT_SECONDS = 8.0
MAX_SITEMAP_FILES = 6
MAX_SITEMAP_URLS = 400
MAX_CONTEXT_HEADINGS = 14
MAX_CONTEXT_NAV_LABELS = 20
MAX_CONTEXT_SCRIPT_URLS = 30
MAX_INTERACTION_CLICKS = 3
NO_CONTEXT_VALUE = "(none)"
DEFAULT_USER_AGENT = "doc-ingestor/1.0"
SEED_DISCOVERY_HEARTBEAT_SECONDS = 20.0
DOC_LABEL_HINTS_PATTERN = (
    r"docs?|documentation|api|reference|guide|tutorial|learn|menu|nav|sidebar|module|namespace"
)
NON_DOC_ASSET_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".mp4",
    ".mp3",
    ".ico",
)
BLOCKED_SEED_FILE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".css",
    ".js",
    ".pdf",
    ".zip",
)

ANALYSIS_SYSTEM_PROMPT = (
    "You are an expert documentation crawling strategist. "
    "Given a documentation start URL, infer high-value seed URLs that maximize coverage "
    "for recursive crawling and downstream LLM indexing."
)


@dataclass(frozen=True)
class SeedDiscoveryDiagnostics:
    llm_requested: bool
    llm_attempted: bool
    llm_used: bool
    llm_reason: str
    llm_candidate_count: int


@dataclass(frozen=True)
class PageSeedContext:
    title: str
    headings: list[str]
    nav_labels: list[str]
    internal_links: list[str]
    script_urls: list[str]
    iframe_urls: list[str]
    interaction_urls: list[str]
    network_urls: list[str]
    final_url: str


class _HeartbeatLogger:
    def __init__(self, label: str, interval_seconds: float = SEED_DISCOVERY_HEARTBEAT_SECONDS):
        self._label = label
        self._interval_seconds = max(5.0, interval_seconds)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time = 0.0

    def __enter__(self) -> "_HeartbeatLogger":
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.2)

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            elapsed = int(time.monotonic() - self._start_time)
            print(
                f"Seed discovery: still looking for potential seeds via {self._label} ({elapsed}s elapsed)...",
                file=sys.stderr,
            )


def discover_seed_urls(
    start_url: str,
    max_seed_urls: int = 8,
    use_llm: bool = False,
    llm_model: str = DEFAULT_LLM_SEED_MODEL,
    use_web_search: bool = False,
) -> list[str]:
    seed_urls, _ = discover_seed_urls_with_diagnostics(
        start_url=start_url,
        max_seed_urls=max_seed_urls,
        use_llm=use_llm,
        llm_model=llm_model,
        use_web_search=use_web_search,
    )
    return seed_urls


def discover_seed_urls_with_diagnostics(
    start_url: str,
    max_seed_urls: int = 8,
    use_llm: bool = False,
    llm_model: str = DEFAULT_LLM_SEED_MODEL,
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

        # Trust Gemma seeds when available; only use filtered heuristic fallback if LLM fails.
        if llm_candidates:
            llm_selected = sorted(
                candidate for candidate in llm_candidates if candidate and candidate != normalized_start
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



def _llm_seed_candidates(
    start_url: str,
    start_parsed: ParseResult,
    page_links: list[str],
    page_context: PageSeedContext,
    deterministic_candidates: list[str],
    llm_model: str,
    max_candidates: int,
    use_web_search: bool,
) -> tuple[set[str], str]:
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if not api_key:
        return set(), "missing-api-key"

    try:
        ollama_module = importlib.import_module("ollama")
        client_cls = getattr(ollama_module, "Client", None)
        if client_cls is None:
            return set(), "ollama-client-missing"
    except Exception:
        return set(), "ollama-package-missing"

    analysis_prompt = _build_llm_analysis_prompt(
        start_url=start_url,
        start_parsed=start_parsed,
        page_links=page_links,
        page_context=page_context,
        deterministic_candidates=deterministic_candidates,
        max_candidates=max_candidates,
    )

    extraction_prompt_template = (
        "Extract all absolute URLs from the following analysis and return ONLY a JSON array of strings.\n"
        "Rules:\n"
        f"- Same domain only: {start_parsed.netloc}\n"
        "- Exclude images/css/js/assets/download pages.\n"
        f"- Cap output to at most {max(1, max_candidates)} URLs.\n"
        "- Output JSON only, no prose.\n\n"
        "Analysis:\n{analysis_text}"
    )

    try:
        with _HeartbeatLogger(label="Ollama seed analysis"):
            web_search_urls = _llm_optional_web_search(
                use_web_search=use_web_search,
                api_key=api_key,
                start_url=start_url,
                start_parsed=start_parsed,
                max_candidates=max_candidates,
            )

            client = client_cls(
                host="https://ollama.com",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            analysis_text = _llm_generate_analysis_text(
                client=client,
                llm_model=llm_model,
                analysis_prompt=analysis_prompt,
                use_web_search=use_web_search,
            )
            if not analysis_text:
                return set(), "empty-llm-analysis"

            extraction_text = _llm_extract_seed_text(
                client=client,
                llm_model=llm_model,
                extraction_prompt=extraction_prompt_template.format(analysis_text=analysis_text),
                use_web_search=use_web_search,
            )
            if not extraction_text:
                return set(), "empty-llm-extraction"

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


def _ollama_web_search_seed_urls(
    api_key: str,
    start_url: str,
    start_parsed: ParseResult,
    max_candidates: int,
) -> set[str]:
    query = (
        f"site:{start_parsed.netloc} documentation seed URLs "
        f"reference api index module namespace for {start_url}"
    )
    body = json.dumps({"query": query, "max_results": max(5, max_candidates)}).encode("utf-8")
    request = Request(
        "https://ollama.com/api/web_search",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
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


def _build_llm_analysis_prompt(
    start_url: str,
    start_parsed: ParseResult,
    page_links: list[str],
    page_context: PageSeedContext,
    deterministic_candidates: list[str],
    max_candidates: int,
) -> str:
    links_excerpt = _excerpt_lines(page_links, MAX_LLM_CONTEXT_LINKS)
    headings_excerpt = _excerpt_lines(page_context.headings, MAX_CONTEXT_HEADINGS)
    nav_excerpt = _excerpt_lines(page_context.nav_labels, MAX_CONTEXT_NAV_LABELS)
    scripts_excerpt = _excerpt_lines(page_context.script_urls, MAX_CONTEXT_SCRIPT_URLS)
    iframe_excerpt = _excerpt_lines(page_context.iframe_urls, MAX_CONTEXT_SCRIPT_URLS)
    interaction_excerpt = _excerpt_lines(page_context.interaction_urls, MAX_LLM_CONTEXT_LINKS)
    network_excerpt = _excerpt_lines(page_context.network_urls, MAX_LLM_CONTEXT_LINKS)
    deterministic_excerpt = _excerpt_lines(deterministic_candidates, MAX_LLM_CONTEXT_LINKS)

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
        "Task:\n"
        "1) Analyze the likely documentation structure for this URL.\n"
        "2) Propose high-value seed URLs (top-level indexes/namespaces/clusters).\n"
        "3) Keep every URL absolute and on the allowed domain.\n"
        "4) Prefer pages/directories that maximize coverage quickly."
    )


def _excerpt_lines(values: list[str], limit: int) -> str:
    return "\n".join(values[:limit]) or NO_CONTEXT_VALUE


def _llm_optional_web_search(
    use_web_search: bool,
    api_key: str,
    start_url: str,
    start_parsed: ParseResult,
    max_candidates: int,
) -> set[str]:
    if not use_web_search:
        return set()
    return _ollama_web_search_seed_urls(
        api_key=api_key,
        start_url=start_url,
        start_parsed=start_parsed,
        max_candidates=max_candidates,
    )


def _llm_generate_analysis_text(
    client: object,
    llm_model: str,
    analysis_prompt: str,
    use_web_search: bool,
) -> str:
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
    return _extract_message_content(client.chat(**kwargs))


def _llm_extract_seed_text(
    client: object,
    llm_model: str,
    extraction_prompt: str,
    use_web_search: bool,
) -> str:
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
    return _extract_message_content(client.chat(**kwargs))


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


def _build_page_seed_context(start_url: str, start_parsed: ParseResult) -> PageSeedContext:
    title = ""
    headings: list[str] = []
    nav_labels: list[str] = []
    internal_links: set[str] = set()
    final_url = start_url

    try:
        record = extract_page(start_url)
        title = record.get("title", "")
        normalized_links = {_normalize_url(link) for link in record.get("links", [])}
        internal_links.update(
            link
            for link in normalized_links
            if link and _same_domain(link, start_parsed)
        )
    except Exception as exc:
        print(f"Seed discovery: page extraction failed for {start_url}: {exc}", file=sys.stderr)

    script_urls: set[str] = set()
    iframe_urls: set[str] = set()
    interaction_urls: set[str] = set()
    network_urls: set[str] = set()

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return PageSeedContext(
            title=title,
            headings=headings,
            nav_labels=nav_labels,
            internal_links=sorted(internal_links),
            script_urls=[],
            iframe_urls=[],
            interaction_urls=[],
            network_urls=[],
            final_url=final_url,
        )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()

            def _on_response(response: object) -> None:
                response_url = _normalize_url(getattr(response, "url", ""))
                if not response_url or not _same_domain(response_url, start_parsed):
                    return
                if _looks_like_non_doc_asset(response_url):
                    return
                network_urls.add(response_url)

            context.on("response", _on_response)
            page = context.new_page()
            page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass

            final_url = _normalize_url(page.url) or start_url
            html = page.content()
            parsed_signals = _extract_html_seed_signals(html=html, base_url=final_url)

            if not title:
                title = parsed_signals["title"]
            headings = parsed_signals["headings"]
            nav_labels = parsed_signals["nav_labels"]
            script_urls.update(
                url
                for url in parsed_signals["script_urls"]
                if _same_domain(url, start_parsed)
            )
            iframe_urls.update(
                url
                for url in parsed_signals["iframe_urls"]
                if _same_domain(url, start_parsed)
            )
            internal_links.update(
                url
                for url in parsed_signals["link_urls"]
                if _same_domain(url, start_parsed)
            )

            interaction_urls.update(_collect_internal_anchors_from_dom(page, start_parsed))
            interaction_urls.update(_run_lightweight_interactions(page, start_parsed))
            interaction_urls.update(_collect_internal_anchors_from_dom(page, start_parsed))

            browser.close()
    except Exception as exc:
        print(f"Seed discovery: browser context failed for {start_url}: {exc}", file=sys.stderr)

    return PageSeedContext(
        title=title,
        headings=headings,
        nav_labels=nav_labels,
        internal_links=sorted(
            url
            for url in internal_links
            if _is_viable_seed_link(url, start_parsed)
        ),
        script_urls=sorted(script_urls),
        iframe_urls=sorted(iframe_urls),
        interaction_urls=sorted(
            url
            for url in interaction_urls
            if _is_viable_seed_link(url, start_parsed)
        ),
        network_urls=sorted(
            url
            for url in network_urls
            if _is_viable_seed_link(url, start_parsed)
        ),
        final_url=final_url,
    )


def _extract_html_seed_signals(html: str, base_url: str) -> dict[str, object]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    title = _clean_html_text(title_match.group(1)) if title_match else ""
    headings = _extract_headings(html)

    link_urls = _extract_tag_attr_urls(html=html, tag="a", attr="href", base_url=base_url)
    script_urls = _extract_tag_attr_urls(html=html, tag="script", attr="src", base_url=base_url)
    iframe_urls = _extract_tag_attr_urls(html=html, tag="iframe", attr="src", base_url=base_url)

    nav_labels = _extract_nav_labels(html)

    return {
        "title": title,
        "headings": headings,
        "nav_labels": nav_labels,
        "link_urls": sorted(link_urls),
        "script_urls": sorted(script_urls),
        "iframe_urls": sorted(iframe_urls),
    }


def _extract_tag_attr_urls(html: str, tag: str, attr: str, base_url: str) -> set[str]:
    pattern = rf"<{tag}\b[^>]*\b{attr}=['\"]([^'\"]+)['\"][^>]*>"
    urls: set[str] = set()
    for match in re.finditer(pattern, html, flags=re.IGNORECASE):
        resolved = _normalize_url(urljoin(base_url, match.group(1)))
        if resolved:
            urls.add(resolved)
    return urls


def _extract_headings(html: str) -> list[str]:
    headings: list[str] = []
    for match in re.finditer(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, flags=re.IGNORECASE | re.DOTALL):
        text = _clean_html_text(match.group(1))
        if text and text not in headings:
            headings.append(text)
        if len(headings) >= MAX_CONTEXT_HEADINGS:
            break
    return headings


def _extract_nav_labels(html: str) -> list[str]:
    labels: list[str] = []
    for match in re.finditer(r"<a[^>]*>(.*?)</a>", html, flags=re.IGNORECASE | re.DOTALL):
        label = _clean_html_text(match.group(1))
        if not label or label in labels:
            continue
        if not re.search(DOC_LABEL_HINTS_PATTERN, label, flags=re.IGNORECASE):
            continue
        labels.append(label)
        if len(labels) >= MAX_CONTEXT_NAV_LABELS:
            break
    return labels


def _collect_internal_anchors_from_dom(page: object, start_parsed: ParseResult) -> set[str]:
    try:
        hrefs = page.eval_on_selector_all("a[href]", "nodes => nodes.map(node => node.href)")
    except Exception:
        return set()

    if not isinstance(hrefs, list):
        return set()

    normalized = {_normalize_url(str(href)) for href in hrefs}
    return {
        url
        for url in normalized
        if url and _same_domain(url, start_parsed) and not _looks_like_non_doc_asset(url)
    }


def _run_lightweight_interactions(page: object, start_parsed: ParseResult) -> set[str]:
    discovered: set[str] = set()
    selector = "button, summary, [role='button'], [role='tab'], [aria-controls], a"
    clicks = 0
    try:
        elements = page.query_selector_all(selector)
    except Exception:
        return discovered

    for element in elements:
        if clicks >= MAX_INTERACTION_CLICKS:
            break

        text = _safe_element_text(element)
        if text and not re.search(DOC_LABEL_HINTS_PATTERN, text):
            continue
        normalized_href = _safe_element_href(element)
        if normalized_href and _same_domain(normalized_href, start_parsed):
            discovered.add(normalized_href)

        if _click_and_collect(page, element, start_parsed, discovered):
            clicks += 1

    return {
        url
        for url in discovered
        if _is_viable_seed_link(url, start_parsed)
    }


def _robots_and_sitemap_candidates(start_parsed: ParseResult) -> set[str]:
    base = f"{start_parsed.scheme}://{start_parsed.netloc}"
    robots_url = f"{base}/robots.txt"
    sitemap_urls = _discover_sitemap_urls_from_robots(
        robots_url=robots_url,
        default_sitemap_url=f"{base}/sitemap.xml",
        start_parsed=start_parsed,
    )
    return _collect_seed_urls_from_sitemaps(start_parsed=start_parsed, sitemap_urls=sitemap_urls)


def _discover_sitemap_urls_from_robots(
    robots_url: str,
    default_sitemap_url: str,
    start_parsed: ParseResult,
) -> set[str]:
    sitemap_urls: set[str] = {default_sitemap_url}
    text = _fetch_text_url(robots_url, ROBOTS_TIMEOUT_SECONDS)
    if not text:
        return sitemap_urls

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.lower().startswith("sitemap:"):
            continue
        candidate = _normalize_url(line.split(":", 1)[1].strip())
        if candidate and _same_domain(candidate, start_parsed):
            sitemap_urls.add(candidate)
    return sitemap_urls


def _collect_seed_urls_from_sitemaps(start_parsed: ParseResult, sitemap_urls: set[str]) -> set[str]:
    results: set[str] = set()
    visited_sitemaps: set[str] = set()
    queue = list(sitemap_urls)

    while queue and len(visited_sitemaps) < MAX_SITEMAP_FILES and len(results) < MAX_SITEMAP_URLS:
        sitemap = queue.pop(0)
        if sitemap in visited_sitemaps:
            continue
        visited_sitemaps.add(sitemap)

        body = _fetch_text_url(sitemap, SITEMAP_TIMEOUT_SECONDS)
        if not body:
            continue

        _consume_sitemap_locs(
            body=body,
            start_parsed=start_parsed,
            results=results,
            visited_sitemaps=visited_sitemaps,
            queue=queue,
        )
    return results


def _consume_sitemap_locs(
    body: str,
    start_parsed: ParseResult,
    results: set[str],
    visited_sitemaps: set[str],
    queue: list[str],
) -> None:
    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", body, flags=re.IGNORECASE)
    for loc in locs:
        candidate = _normalize_url(unescape(loc.strip()))
        if not candidate or not _same_domain(candidate, start_parsed):
            continue
        if candidate.endswith(".xml") and "sitemap" in candidate.lower():
            if candidate not in visited_sitemaps:
                queue.append(candidate)
            continue
        if _is_viable_seed_link(candidate, start_parsed):
            results.add(candidate)
        if len(results) >= MAX_SITEMAP_URLS:
            break


def _fetch_text_url(url: str, timeout_seconds: float) -> str:
    try:
        request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT}, method="GET")
        with urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _safe_element_text(element: object) -> str:
    try:
        return (element.inner_text(timeout=800) or "").strip().lower()
    except Exception:
        return ""


def _safe_element_href(element: object) -> str:
    try:
        return _normalize_url((element.get_attribute("href") or "").strip())
    except Exception:
        return ""


def _click_and_collect(page: object, element: object, start_parsed: ParseResult, discovered: set[str]) -> bool:
    try:
        element.scroll_into_view_if_needed(timeout=1_000)
        element.click(timeout=1_500)
        page.wait_for_timeout(400)
        current_url = _normalize_url(page.url)
        if current_url and _same_domain(current_url, start_parsed):
            discovered.add(current_url)
        discovered.update(_collect_internal_anchors_from_dom(page, start_parsed))
        return True
    except Exception:
        return False


def _clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    normalized = " ".join(unescape(without_tags).split())
    return normalized.strip()


def _looks_like_non_doc_asset(url: str) -> bool:
    lowered = urlparse(url).path.lower()
    return any(lowered.endswith(ext) for ext in NON_DOC_ASSET_EXTENSIONS)


def _extract_message_content(response: object) -> str:
    dict_content = _extract_message_content_from_dict(response)
    if dict_content:
        return dict_content

    object_content = _extract_message_content_from_object(response)
    if object_content:
        return object_content

    return ""


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


def _select_live_candidates(
    ranked_candidates: list[str],
    start_parsed: ParseResult,
    max_count: int,
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

    # Fallback for restrictive sites that block HEAD/GET probing.
    return ranked_candidates[:max_count]


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
