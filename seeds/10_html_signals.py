

"""HTML signal extraction and lightweight browser interactions.

Extracts links, headings, navigation labels, scripts, and simple click-expanded anchors
from documentation homepages before sitemap probing begins.
"""

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
