

"""llms.txt Markdown parsing helpers.

Converts full llms.txt documents and embedded page wrappers into ``DocPageRecord`` values,
including metadata extraction, heading inference, and section splitting.
"""

def _parse_llms_full_content(content: str, source_url: str) -> list[DocPageRecord]:
    page_records = _parse_llms_page_blocks(content, source_url)
    if page_records:
        return page_records

    base_url = source_url.split("#", 1)[0].rstrip("/")
    sections = _split_llms_markdown_sections(content)
    records: list[DocPageRecord] = []
    seen_slugs: dict[str, int] = {}

    for idx, section in enumerate(sections):
        if not section.strip():
            continue
        section = section.strip()
        lines = section.splitlines()
        title = _clean_llms_title(lines[0]) if lines else f"Section {idx + 1}"
        body = "\n".join(lines[1:]).strip()
        if not body:
            continue
        slug = _unique_slug(title, seen_slugs)
        content_blocks, code_blocks = _parse_content(body)
        record: DocPageRecord = {
            "url": f"{base_url}#{slug}",
            "canonical_url": f"{base_url}#{slug}",
            "depth": 0,
            "order_index": idx,
            "title": title,
            "content_blocks": content_blocks,
            "code_blocks": code_blocks,
            "links": [],
            "metadata": {"source_domain": urlparse(source_url).netloc or None, "breadcrumbs": []},
            "errors": [],
        }
        records.append(record)
    return records


def _parse_llms_page_blocks(content: str, source_url: str) -> list[DocPageRecord]:
    page_pattern = re.compile(
        r"<page\b(?P<attrs>[^>]*)>\s*<!\[CDATA\[(?P<body>.*?)\]\]>\s*</page>",
        re.DOTALL | re.IGNORECASE,
    )
    matches = list(page_pattern.finditer(content))
    if not matches:
        return []

    source_base = source_url.split("#", 1)[0]
    source_parsed = urlparse(source_base)
    origin = f"{source_parsed.scheme}://{source_parsed.netloc}"
    records: list[DocPageRecord] = []

    for idx, match in enumerate(matches):
        attrs = _parse_page_attrs(match.group("attrs"))
        body = html.unescape(match.group("body").strip())
        explicit_url, body = _extract_llms_metadata_line(body, "URL")
        description, body = _extract_llms_metadata_line(body, "Description")

        title = attrs.get("title") or _first_markdown_heading(body) or f"Page {idx + 1}"
        path = attrs.get("path") or ""
        page_url = explicit_url or (urljoin(origin, path) if path else f"{source_base}#page-{idx + 1}")
        content_text = body.strip()
        if description:
            content_text = f"{description.strip()}\n\n{content_text}" if content_text else description.strip()
        if not content_text:
            continue

        content_blocks, code_blocks = _parse_content(content_text)
        records.append(
            {
                "url": page_url,
                "canonical_url": page_url,
                "depth": 0,
                "order_index": idx,
                "title": html.unescape(title).strip(),
                "content_blocks": content_blocks,
                "code_blocks": code_blocks,
                "links": [],
                "metadata": {
                    "source_domain": source_parsed.netloc or None,
                    "breadcrumbs": [],
                    "llms_source": source_base,
                    "path": path or None,
                },
                "errors": [],
            }
        )

    return records


def _parse_page_attrs(attrs: str) -> dict[str, str]:
    return {
        name.lower(): html.unescape(value)
        for name, value in re.findall(r'(\w+)="([^"]*)"', attrs)
    }


def _clean_llms_title(title: str) -> str:
    title = html.unescape(title).strip()
    title = re.sub(r"^\s{0,3}#{1,6}\s+", "", title).strip()
    return title or "Untitled"


def _unique_slug(title: str, seen_slugs: dict[str, int]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "section"
    count = seen_slugs.get(base, 0)
    seen_slugs[base] = count + 1
    return base if count == 0 else f"{base}-{count + 1}"


def _extract_llms_metadata_line(body: str, key: str) -> tuple[str | None, str]:
    match = re.match(rf"\s*{re.escape(key)}:\s*(.*?)\s*(?:\r?\n|$)", body, flags=re.IGNORECASE)
    if not match:
        return None, body
    return match.group(1).strip(), body[match.end():].lstrip()


def _first_markdown_heading(body: str) -> str | None:
    match = re.search(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", body, flags=re.MULTILINE)
    return _clean_llms_title(match.group(0)) if match else None


def _split_llms_markdown_sections(content: str) -> list[str]:
    h2_sections = _split_markdown_at_heading(content, 2)
    if not h2_sections:
        return [content]

    word_counts = [len(section.split()) for section in h2_sections]
    has_many_h3 = len(re.findall(r"^###\s+", content, flags=re.MULTILINE)) >= 10
    max_words = max(word_counts, default=0)
    if len(h2_sections) <= 10 and max_words > 3000 and has_many_h3:
        return _split_markdown_at_heading(content, 3) or h2_sections
    return h2_sections
