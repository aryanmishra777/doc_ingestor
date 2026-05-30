

"""Page-context collection for LLM seed prompts.

Fetches the start page with browser and HTTP fallbacks, gathers headings, navigation
labels, internal links, script URLs, and interaction-discovered anchors.
"""

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
