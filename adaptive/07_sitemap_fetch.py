

"""Sitemap fetching plus shared Markdown section helpers.

Completes llms.txt section cleanup, then fetches sitemap indexes/documents and turns their
references into a bounded URL queue for adaptive collection.
"""

def _split_markdown_at_heading(content: str, level: int) -> list[str]:
    marker = "#" * level
    pattern = re.compile(rf"^{re.escape(marker)}\s+(.+)$", flags=re.MULTILINE)
    matches = list(pattern.finditer(content))
    if not matches:
        return []

    sections: list[str] = []
    intro = content[: matches[0].start()].strip()
    if intro:
        sections.append(intro)
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        sections.append(content[match.start():end].strip())
    return sections


def _clean_llms_title(title: str) -> str:
    title = html.unescape(title).strip()
    title = re.sub(r"^\s{0,3}#{1,6}\s+", "", title).strip()
    return title or "Untitled"


def _unique_slug(title: str, seen_slugs: dict[str, int]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "section"
    count = seen_slugs.get(base, 0)
    seen_slugs[base] = count + 1
    return base if count == 0 else f"{base}-{count + 1}"


# ---------------------------------------------------------------------------
# Deterministic handler: sitemap.xml
# ---------------------------------------------------------------------------

def _handle_fetch_sitemap(state: AgentState, log: Callable[[str], None]) -> None:
    urls = _parse_sitemap_urls(
        state.detection.url,
        state.target_url,
        initial_body=state.detection.prefetched_content,
        max_urls=state.crawler_kwargs.get("max_pages"),
    )
    if not urls:
        log("Adaptive: sitemap contained no usable URLs, falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return
    # If the user passed the sitemap URL itself as the start URL, that URL is
    # not a useful BFS entry point (XML, no outbound doc links). Rewrite
    # target_url to the first discovered sitemap entry so any later crawler
    # fallback can BFS from a real documentation page.
    if _is_sitemap_file_url(state.target_url):
        log(f"Adaptive: start URL is a sitemap file, using {urls[0]} as crawl entry point")
        state.target_url = urls[0]
    log(f"Adaptive: sitemap yielded {len(urls)} URLs, fetching...")
    workers = state.crawler_kwargs.get("max_workers", 4)
    include_sparse = state.crawler_kwargs.get("include_sparse_pages", False)
    state.doc_records = _fetch_url_list(urls, max_workers=workers, log=log, include_sparse_pages=include_sparse)
    log(f"Adaptive: fetched {len(state.doc_records)} records from sitemap")
    state.phase = CrawlerPhase.EVALUATE_QUALITY


def _collect_sitemap_refs(root: ET.Element, ns_prefix: str, queue: list[str]) -> None:
    for sitemap_elem in root.findall(f"{ns_prefix}sitemap"):
        loc = sitemap_elem.find(f"{ns_prefix}loc")
        if loc is not None and loc.text:
            queue.append(loc.text.strip())


def _collect_sitemap_urls(
    root: ET.Element,
    ns_prefix: str,
    target_domain: str,
    restrict_to_prefix: bool,
    start_prefix: str,
    urls: list[str],
    max_urls: int | None,
) -> None:
    for url_elem in root.findall(f"{ns_prefix}url"):
        loc = url_elem.find(f"{ns_prefix}loc")
        if loc is None or not loc.text:
            continue
        url = loc.text.strip()
        parsed = urlparse(url)
        if parsed.netloc.lower() != target_domain:
            continue
        path_lower = parsed.path.lower()
        if any(path_lower.endswith(ext) for ext in _ASSET_EXTENSIONS):
            continue
        if restrict_to_prefix and not path_lower.startswith(start_prefix):
            continue
        urls.append(url)
        if max_urls is not None and len(urls) >= max_urls:
            break


def _process_sitemap_document(
    root: ET.Element,
    target_domain: str,
    restrict_to_prefix: bool,
    start_prefix: str,
    urls: list[str],
    queue: list[str],
    max_urls: int | None,
) -> None:
    ns_match = re.match(r"\{([^}]+)\}", root.tag)
    ns_prefix = f"{{{ns_match.group(1)}}}" if ns_match else ""
    if "sitemapindex" in root.tag:
        _collect_sitemap_refs(root, ns_prefix, queue)
    else:
        _collect_sitemap_urls(root, ns_prefix, target_domain, restrict_to_prefix, start_prefix, urls, max_urls)
