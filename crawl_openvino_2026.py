"""One-off: crawl docs.openvino.ai/2026/ via the 2025 sitemap.

The OpenVINO sitemap currently only lists /2025/ URLs, but the /2026/ pages
exist at the same paths. This script rewrites 2025 -> 2026 and fetches each
page in parallel, then writes chunked markdown using the existing pipeline.

Run from the project root:
    ./venv/Scripts/python.exe crawl_openvino_2026.py
"""
from __future__ import annotations

import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adaptive import _http_get
from cleaning import clean_record
from extraction import extract_from_html
from models import DocPageRecord, make_error_record
from pipeline import write_markdown_outputs

SITEMAP_URL = "https://docs.openvino.ai/sitemap.xml"
OUTPUT = Path("OpenVINO_2026_docs.md")
# 30 workers triggered server-side throttling (~1.2 pages/s overall). Backing
# off to 12 to avoid the rate-limit penalty — actual concurrent in-flight drops
# but per-request latency drops more.
WORKERS = 30
CHUNK_PAGES = 200 

# Skip the obvious junk so we don't waste worker time on non-HTML targets.
_ASSET_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".map", ".zip", ".tar", ".gz", ".mp4",
)


def fetch_sitemap_urls() -> list[str]:
    r = _http_get(SITEMAP_URL, read_limit=16 * 1024 * 1024, timeout=30.0)
    if not r or r["status"] != 200:
        raise RuntimeError(f"failed to fetch sitemap: {r}")
    body = r["body"]
    root = ET.fromstring(body)
    ns_match = re.match(r"\{([^}]+)\}", root.tag)
    ns = f"{{{ns_match.group(1)}}}" if ns_match else ""
    urls: list[str] = []
    for url_elem in root.findall(f"{ns}url"):
        loc = url_elem.find(f"{ns}loc")
        if loc is None or not loc.text:
            continue
        urls.append(loc.text.strip())
    return urls


def rewrite_to_2026(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "docs.openvino.ai":
        return None
    path = parsed.path
    if not path.startswith("/2025/"):
        return None
    new_path = "/2026/" + path[len("/2025/"):]
    if any(new_path.lower().endswith(ext) for ext in _ASSET_SUFFIXES):
        return None
    return parsed._replace(path=new_path).geturl()


def fetch_one(url: str, idx: int) -> DocPageRecord:
    r = _http_get(url, read_limit=4 * 1024 * 1024, timeout=30.0)
    if not r or r["status"] != 200:
        status = r["status"] if r else "connection failed"
        return make_error_record(url, 0, idx, f"HTTP {status}", RuntimeError(str(status)))
    raw = extract_from_html(r["body"], url=url, depth=0, order_index=idx)
    return clean_record(raw)


def main() -> None:
    print(f"Fetching sitemap from {SITEMAP_URL}...", file=sys.stderr)
    raw_urls = fetch_sitemap_urls()
    print(f"Sitemap had {len(raw_urls)} entries", file=sys.stderr)

    rewritten = [u for u in (rewrite_to_2026(u) for u in raw_urls) if u]
    # Dedupe while preserving order
    seen: set[str] = set()
    targets: list[str] = []
    for u in rewritten:
        if u not in seen:
            seen.add(u)
            targets.append(u)
    print(f"After 2025->2026 rewrite + filter: {len(targets)} unique URLs", file=sys.stderr)

    records: list[DocPageRecord] = []
    failures = 0
    started = time.monotonic()
    total = len(targets)

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(fetch_one, url, idx): url for idx, url in enumerate(targets)}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                record = fut.result()
            except Exception as exc:
                failures += 1
                print(f"  ERROR  {url}: {exc}", file=sys.stderr)
                continue

            if record.get("errors"):
                failures += 1
            records.append(record)

            done = len(records)
            if done % 50 == 0 or done == total:
                rate = done / max(1e-6, time.monotonic() - started)
                print(
                    f"  progress: {done}/{total} pages "
                    f"(failures={failures}, {rate:.1f} pages/s)",
                    file=sys.stderr,
                )

    elapsed = time.monotonic() - started
    print(
        f"Done: {len(records)} records "
        f"(failures={failures}, {elapsed:.1f}s, {len(records)/elapsed:.1f} pages/s)",
        file=sys.stderr,
    )

    # Reassign order_index by sorted URL so the markdown is reproducible regardless
    # of which futures completed first.
    records.sort(key=lambda r: r.get("url") or "")
    for i, r in enumerate(records):
        r["order_index"] = i

    written = write_markdown_outputs(records, OUTPUT, chunk_pages=CHUNK_PAGES)
    print(f"Wrote {len(written)} markdown file(s):", file=sys.stderr)
    for p in written:
        print(f"  {p}", file=sys.stderr)


if __name__ == "__main__":
    main()
