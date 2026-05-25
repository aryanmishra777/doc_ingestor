from __future__ import annotations

import gzip
import html
import importlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

import requests

try:
    from .cleaning import clean_record
    from .extraction import extract_from_html
    from .markdown_extraction import extract_markdown
    from .models import CodeBlock, ContentBlock, DocPageRecord, make_error_record
    from .pdf_extraction import extract_pdf
    from .pipeline import PipelineStats, collect_records
except ImportError:
    from cleaning import clean_record
    from extraction import extract_from_html
    from markdown_extraction import extract_markdown
    from models import CodeBlock, ContentBlock, DocPageRecord, make_error_record
    from pdf_extraction import extract_pdf
    from pipeline import PipelineStats, collect_records

PROBE_TIMEOUT = 5.0
SITEMAP_TIMEOUT = 20.0
PAGE_FETCH_TIMEOUT = 30.0
PAGE_READ_LIMIT = 2 * 1024 * 1024  # 2 MB — enough for any documentation page
LLMS_TXT_READ_LIMIT = 8 * 1024 * 1024
MAX_RETRIES = 3
MAX_SITEMAP_FILES = 10
MAX_SITEMAP_URLS = 2000
DEFAULT_OLLAMA_PROVIDER = "cloud"
DEFAULT_CLOUD_ADAPTIVE_MODEL = "gemma4:31b-cloud"
DEFAULT_LOCAL_ADAPTIVE_MODEL = "gemma4:latest"
DEFAULT_GEMINI_ADAPTIVE_MODEL = "gemini-2.5-flash-lite"
DEFAULT_ADAPTIVE_MODEL = DEFAULT_CLOUD_ADAPTIVE_MODEL
LOCAL_OLLAMA_HOST = "http://localhost:11434"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_USER_AGENT = "doc-ingestor/1.0"

_ASSET_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".map", ".zip", ".tar", ".gz", ".mp4", ".mov", ".avi",
)

_FRAMEWORK_SIGNALS: dict[str, list[str]] = {
    "docusaurus": ['<meta name="generator" content="Docusaurus', '<div id="__docusaurus">'],
    "gitbook": ['<meta name="generator" content="GitBook"'],
    "readthedocs": ["window.READTHEDOCS_DATA"],
    "mkdocs": ['<meta name="generator" content="mkdocs-'],
}

_SCRIPT_SYSTEM = """\
You are a senior Python data extraction engineer. Write a single self-contained Python script \
that fetches documentation content from a given URL.

RULES:
1. Output ONLY valid executable Python code — no markdown fences, no explanations.
2. Print results to sys.stdout as JSON Lines — one JSON object per page.
3. Print NOTHING else to sys.stdout. Route all logs and errors to sys.stderr.
4. Use only stdlib plus requests and beautifulsoup4.
5. Handle HTTP errors gracefully — log to stderr and skip failed pages.

REQUIRED OUTPUT SCHEMA per line printed to stdout:
{"url": "<absolute URL>", "title": "<H1 or title tag>", "content": "<article prose, no nav or sidebar>", "metadata": {"framework": "<name>", "depth": 0}}
"""

_FEEDBACK_SYSTEM = """\
You are a documentation crawl diagnostics engineer. Analyze the execution trace and return \
ONLY a JSON object — no prose, no markdown fences.

SCHEMA:
{
  "failure_mode": "<SELECTOR_MISMATCH | PAGINATION_FAILURE | RATE_LIMITED | EMPTY_CONTENT | SYNTAX_ERROR | JS_NOT_RENDERED | ANTIBOT | AUTH_REQUIRED | INFINITE_SCROLL>",
  "confidence_score": <float 0.0-1.0>,
  "permanent_fix_recommended": <true | false>,
  "rationale": "<technical explanation of the failure>",
  "immediate_fix": "<concrete change to make in the next attempt>"
}
"""


class DetectionType(str, Enum):
    LLMS_TXT = "llms_txt"
    SITEMAP = "sitemap"
    OPENAPI = "openapi"
    FRAMEWORK = "framework"


class CrawlerPhase(Enum):
    INIT = auto()
    PROBE_API = auto()
    FETCH_LLMS_TXT = auto()
    FETCH_SITEMAP = auto()
    CONVERT_OPENAPI = auto()
    GENERATE_SCRIPT = auto()
    EXECUTE_SCRIPT = auto()
    CRAWLER_FALLBACK = auto()
    EVALUATE_QUALITY = auto()
    SELF_CORRECT = auto()
    FEEDBACK_ANALYSIS = auto()
    DONE = auto()
    FAILED = auto()


@dataclass
class DetectionResult:
    type: DetectionType
    url: str
    framework: str | None = None
    prefetched_content: str | None = None


@dataclass
class AgentState:
    target_url: str
    llm_model: str = DEFAULT_ADAPTIVE_MODEL
    llm_provider: str = DEFAULT_OLLAMA_PROVIDER
    phase: CrawlerPhase = CrawlerPhase.INIT
    detection: DetectionResult | None = None
    generated_code: str | None = None
    script_stdout: list[str] = field(default_factory=list)
    script_stderr: str = ""
    script_returncode: int | None = None
    generation_context: str = ""
    doc_records: list[DocPageRecord] = field(default_factory=list)
    crawler_kwargs: dict[str, Any] = field(default_factory=dict)
    eval_metrics: dict[str, Any] = field(default_factory=dict)
    feedback_report: dict[str, Any] | None = None
    retry_count: int = 0


def collect_records_adaptive(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    logger: Callable[[str], None] | None = None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
    llm_model: str = DEFAULT_ADAPTIVE_MODEL,
    llm_provider: str = DEFAULT_OLLAMA_PROVIDER,
) -> tuple[list[DocPageRecord], PipelineStats]:
    log = logger or _stderr_logger
    state = AgentState(
        target_url=start_url,
        llm_model=llm_model,
        llm_provider=llm_provider,
        crawler_kwargs={
            "max_pages": max_pages,
            "max_depth": max_depth,
            "max_workers": max_workers,
            "include_sparse_pages": include_sparse_pages,
            "logger": log,
        },
    )
    _terminal = {CrawlerPhase.DONE, CrawlerPhase.FAILED}
    while state.phase not in _terminal:
        _run_phase(state, log)

    required_depth = max((r.get("depth") or 0) for r in state.doc_records) if state.doc_records else 0
    stats = PipelineStats(
        pages=len(state.doc_records),
        required_depth=required_depth,
        failed_pages=0,
        truncated_by_page_cap=False,
        depth_cap_reached=False,
    )
    return state.doc_records, stats


# ---------------------------------------------------------------------------
# Phase handler functions (one per CrawlerPhase)
# ---------------------------------------------------------------------------

def _phase_init(state: AgentState, log: Callable[[str], None]) -> None:
    state.phase = CrawlerPhase.PROBE_API


def _phase_probe_api(state: AgentState, log: Callable[[str], None]) -> None:
    log("Adaptive: probing for documentation API endpoints...")
    state.detection = _probe_for_api(state.target_url)
    if state.detection:
        desc = state.detection.framework or state.detection.type.value
        log(f"Adaptive: detected {desc} at {state.detection.url}")
        state.phase = {
            DetectionType.LLMS_TXT: CrawlerPhase.FETCH_LLMS_TXT,
            DetectionType.SITEMAP: CrawlerPhase.FETCH_SITEMAP,
            DetectionType.OPENAPI: CrawlerPhase.CONVERT_OPENAPI,
            DetectionType.FRAMEWORK: CrawlerPhase.GENERATE_SCRIPT,
        }[state.detection.type]
    else:
        log("Adaptive: no API endpoint detected, using standard crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK


def _phase_fetch_llms_txt(state: AgentState, log: Callable[[str], None]) -> None:
    assert state.detection is not None
    log(f"Adaptive: processing llms.txt at {state.detection.url}...")
    _handle_fetch_llms_txt(state, log)


def _phase_fetch_sitemap(state: AgentState, log: Callable[[str], None]) -> None:
    assert state.detection is not None
    log(f"Adaptive: parsing sitemap at {state.detection.url}...")
    _handle_fetch_sitemap(state, log)


def _phase_convert_openapi(state: AgentState, log: Callable[[str], None]) -> None:
    assert state.detection is not None
    log(f"Adaptive: converting OpenAPI spec at {state.detection.url}...")
    _handle_convert_openapi(state, log)


def _phase_generate_script(state: AgentState, log: Callable[[str], None]) -> None:
    log(f"Adaptive: generating fetch script via {state.llm_provider}...")
    code, err = _generate_fetch_script(state, log)
    if err:
        log(f"Adaptive: script generation failed ({err}), falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
    else:
        state.generated_code = code
        state.phase = CrawlerPhase.EXECUTE_SCRIPT


def _phase_execute_script(state: AgentState, log: Callable[[str], None]) -> None:
    log("Adaptive: executing fetch script...")
    lines, stderr, returncode = _execute_script(state.generated_code or "")
    state.script_stdout = lines
    state.script_stderr = stderr
    state.script_returncode = returncode
    if returncode != 0:
        log(f"Adaptive: script exited with code {returncode}")
    state.doc_records = _convert_script_output(lines)
    log(f"Adaptive: script produced {len(state.doc_records)} records")
    state.phase = CrawlerPhase.EVALUATE_QUALITY


def _phase_crawler_fallback(state: AgentState, log: Callable[[str], None]) -> None:
    log("Adaptive: running standard crawler...")
    try:
        records, _ = collect_records(state.target_url, **state.crawler_kwargs)
        state.doc_records = records
        log(f"Adaptive: crawler produced {len(records)} records")
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        log(f"Adaptive: crawler failed: {exc}")
        state.doc_records = []
    state.phase = CrawlerPhase.EVALUATE_QUALITY


def _phase_evaluate_quality(state: AgentState, log: Callable[[str], None]) -> None:
    state.eval_metrics = _evaluate_quality(state.doc_records)
    log(
        "Adaptive: quality — "
        f"structural={state.eval_metrics['structural']:.2f}, "
        f"density={state.eval_metrics['density']:.2f}, "
        f"scope={state.eval_metrics['scope']:.2f}, "
        f"passed={state.eval_metrics['passed']}"
    )
    if state.eval_metrics["passed"]:
        state.phase = CrawlerPhase.DONE
    elif _is_complete_single_document(state.doc_records, state.eval_metrics):
        log("Adaptive: accepting dense single-document output despite low multi-page scope")
        state.phase = CrawlerPhase.DONE
    elif _is_unproductive_crawler_retry(state):
        log("Adaptive: crawler retry did not broaden output, accepting current records")
        state.phase = CrawlerPhase.DONE if state.doc_records else CrawlerPhase.FAILED
    elif state.retry_count < MAX_RETRIES:
        state.retry_count += 1
        log(f"Adaptive: self-correcting (attempt {state.retry_count}/{MAX_RETRIES})...")
        state.phase = CrawlerPhase.SELF_CORRECT
    else:
        log("Adaptive: retry budget exhausted, generating feedback report...")
        state.phase = CrawlerPhase.FEEDBACK_ANALYSIS


def _phase_feedback_analysis(state: AgentState, log: Callable[[str], None]) -> None:
    log("Adaptive: generating XAI feedback report...")
    state.feedback_report = _generate_feedback(state, log)
    if state.feedback_report:
        _emit_feedback_report(state.feedback_report, log)
    state.phase = CrawlerPhase.DONE if state.doc_records else CrawlerPhase.FAILED


_PHASE_DISPATCH: dict[CrawlerPhase, Callable[[AgentState, Callable[[str], None]], None]] = {
    CrawlerPhase.INIT: _phase_init,
    CrawlerPhase.PROBE_API: _phase_probe_api,
    CrawlerPhase.FETCH_LLMS_TXT: _phase_fetch_llms_txt,
    CrawlerPhase.FETCH_SITEMAP: _phase_fetch_sitemap,
    CrawlerPhase.CONVERT_OPENAPI: _phase_convert_openapi,
    CrawlerPhase.GENERATE_SCRIPT: _phase_generate_script,
    CrawlerPhase.EXECUTE_SCRIPT: _phase_execute_script,
    CrawlerPhase.CRAWLER_FALLBACK: _phase_crawler_fallback,
    CrawlerPhase.EVALUATE_QUALITY: _phase_evaluate_quality,
    CrawlerPhase.SELF_CORRECT: lambda s, l: _self_correct(s, l),
    CrawlerPhase.FEEDBACK_ANALYSIS: _phase_feedback_analysis,
}


def _run_phase(state: AgentState, log: Callable[[str], None]) -> None:
    handler = _PHASE_DISPATCH.get(state.phase)
    if handler is not None:
        handler(state, log)


# ---------------------------------------------------------------------------
# Pre-checks: parallel HTTP probes
# ---------------------------------------------------------------------------

def _detect_llms_txt(
    responses: dict[str, dict[str, Any] | None],
    probe_paths: dict[str, str],
    base: str,
) -> DetectionResult | None:
    for key in ("llms_full_1", "llms_full_2", "llms_1", "llms_2"):
        r = responses.get(key)
        if not r or r["status"] != 200:
            continue
        ct = r["content_type"].lower()
        if "text/plain" in ct or "text/markdown" in ct or "markdown" in ct:
            return DetectionResult(
                type=DetectionType.LLMS_TXT,
                url=base + probe_paths[key],
                prefetched_content=r["body"],
            )
    return None


def _detect_sitemap(
    responses: dict[str, dict[str, Any] | None],
    probe_paths: dict[str, str],
    base: str,
) -> DetectionResult | None:
    for key in ("sitemap_1", "sitemap_2"):
        r = responses.get(key)
        if not r or r["status"] != 200:
            continue
        body = r["body"]
        if "<urlset" in body or "<sitemapindex" in body:
            return DetectionResult(
                type=DetectionType.SITEMAP,
                url=base + probe_paths[key],
                prefetched_content=body,
            )
    return None


def _detect_openapi(
    responses: dict[str, dict[str, Any] | None],
    probe_paths: dict[str, str],
    base: str,
) -> DetectionResult | None:
    for key in ("openapi_1", "openapi_2", "openapi_3", "openapi_4"):
        r = responses.get(key)
        if not r or r["status"] != 200:
            continue
        ct = r["content_type"].lower()
        body = r["body"]
        if ("json" in ct or "yaml" in ct) and (
            '"openapi"' in body or '"swagger"' in body or "openapi:" in body
        ):
            return DetectionResult(
                type=DetectionType.OPENAPI,
                url=base + probe_paths[key],
                prefetched_content=body,
            )
    return None


def _detect_framework(
    responses: dict[str, dict[str, Any] | None],
    url: str,
) -> DetectionResult | None:
    r = responses.get("homepage")
    if not r or r["status"] != 200:
        return None
    html = r["body"]
    if "X-ReadTheDocs-Project" in r["headers"]:
        return DetectionResult(type=DetectionType.FRAMEWORK, url=url, framework="readthedocs")
    for framework, signals in _FRAMEWORK_SIGNALS.items():
        if any(s in html for s in signals):
            return DetectionResult(type=DetectionType.FRAMEWORK, url=url, framework=framework)
    return None


def _probe_for_api(url: str) -> DetectionResult | None:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    probe_paths: dict[str, str] = {
        "llms_full_1": "/llms-full.txt",
        "llms_full_2": "/.well-known/llms-full.txt",
        "llms_1":      "/llms.txt",
        "llms_2":      "/.well-known/llms.txt",
        "sitemap_1":   "/sitemap.xml",
        "sitemap_2":   "/sitemap_index.xml",
        "openapi_1":   "/openapi.json",
        "openapi_2":   "/swagger.json",
        "openapi_3":   "/api-docs",
        "openapi_4":   "/.well-known/openapi.yaml",
        "homepage":    "/",
    }

    responses: dict[str, dict[str, Any] | None] = {}
    with ThreadPoolExecutor(max_workers=len(probe_paths)) as executor:
        future_to_key = {
            executor.submit(_http_get, base + path): key
            for key, path in probe_paths.items()
        }
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                responses[key] = future.result()
            except Exception:
                responses[key] = None

    return (
        _detect_llms_txt(responses, probe_paths, base)
        or _detect_sitemap(responses, probe_paths, base)
        or _detect_openapi(responses, probe_paths, base)
        or _detect_framework(responses, url)
    )


def _http_get(
    url: str, read_limit: int = 65536, timeout: float = PROBE_TIMEOUT
) -> dict[str, Any] | None:
    req = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"}, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type", "")
            ce = resp.headers.get("Content-Encoding", "")
            headers = dict(resp.headers)
            needs_decompress = (
                url.lower().endswith(".gz")
                or "gzip" in ce.lower()
                or "application/gzip" in ct.lower()
                or "application/x-gzip" in ct.lower()
            )
            # For gzip streams, read the full body before decompressing; otherwise
            # a partial read would leave the gzip member incomplete and fail.
            raw = resp.read() if needs_decompress else resp.read(read_limit)
            if needs_decompress:
                try:
                    raw = gzip.open(io.BytesIO(raw)).read()
                except Exception:
                    pass
            return {
                "status": resp.getcode(),
                "content_type": ct,
                "headers": headers,
                "body": raw[:read_limit].decode("utf-8", errors="ignore"),
            }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Deterministic handler: llms.txt / llms-full.txt
# ---------------------------------------------------------------------------

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


def _parse_sitemap_urls(
    sitemap_url: str,
    target_url: str,
    initial_body: str | None = None,
    max_urls: int | None = None,
) -> list[str]:
    parsed_target = urlparse(target_url)
    target_domain = parsed_target.netloc.lower()
    start_prefix = _sitemap_start_prefix(parsed_target.path)
    restrict_to_prefix = start_prefix != "/"

    visited: set[str] = set()
    queue = [sitemap_url]
    urls: list[str] = []

    while queue and len(visited) < MAX_SITEMAP_FILES and (max_urls is None or len(urls) < max_urls):
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        body = initial_body if current == sitemap_url else None
        if body is None:
            r = _http_get(current, read_limit=8 * 1024 * 1024, timeout=SITEMAP_TIMEOUT)
            if not r or r["status"] != 200:
                continue
            body = r["body"]

        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            continue

        _process_sitemap_document(root, target_domain, restrict_to_prefix, start_prefix, urls, queue, max_urls)

    return urls


def _is_sitemap_file_url(url: str) -> bool:
    leaf = urlparse(url).path.rsplit("/", 1)[-1].lower()
    return leaf.endswith(".xml") and "sitemap" in leaf


def _sitemap_start_prefix(path: str) -> str:
    normalized = (path or "/").lower()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return "/"

    # If the start URL's leaf segment is a file (e.g. user passed /sitemap.xml
    # or /en/latest/index.html), it is not a directory prefix — strip it so
    # the parent directory is used instead. Without this, the file path gets
    # appended with "/" and rejects every URL in the sitemap.
    if "." in parts[-1]:
        parts = parts[:-1]
        if not parts:
            return "/"

    docs_index = parts.index("docs") if "docs" in parts else -1
    if docs_index >= 0:
        if len(parts) == docs_index + 1:
            return "/" + "/".join(parts[: docs_index + 1]) + "/"
        next_part = parts[docs_index + 1]
        if next_part in {"home", "index", "overview", "documentation"}:
            return "/" + "/".join(parts[: docs_index + 1]) + "/"

    return "/" + "/".join(parts) + "/"


# ---------------------------------------------------------------------------
# Deterministic handler: OpenAPI / Swagger
# ---------------------------------------------------------------------------

def _handle_convert_openapi(state: AgentState, log: Callable[[str], None]) -> None:
    content = state.detection.prefetched_content or ""
    if not content:
        r = _http_get(state.detection.url, read_limit=4 * 1024 * 1024)
        content = r["body"] if r and r["status"] == 200 else ""

    if not content:
        log("Adaptive: OpenAPI spec empty or unreadable, falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return

    try:
        spec = json.loads(content)
    except json.JSONDecodeError:
        log("Adaptive: OpenAPI spec is not valid JSON, falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return

    records = _convert_openapi_to_records(spec, state.detection.url)
    if not records:
        log("Adaptive: OpenAPI spec yielded no records, falling back to crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return

    log(f"Adaptive: converted {len(records)} endpoint records from OpenAPI spec")
    state.doc_records = records
    state.phase = CrawlerPhase.EVALUATE_QUALITY


def _convert_openapi_to_records(spec: dict[str, Any], spec_url: str) -> list[DocPageRecord]:
    api_title = spec.get("info", {}).get("title", "API")
    source_domain = urlparse(spec_url).netloc or None
    _HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
    records: list[DocPageRecord] = []

    for idx, (path, path_item) in enumerate(spec.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            record = _build_operation_record(
                operation, method, path, spec_url, api_title, source_domain, idx
            )
            records.append(record)

    return records


def _build_param_lines(parameters: list[Any]) -> list[str]:
    return [
        f"{p['name']} ({p.get('in', '')}, {'required' if p.get('required') else 'optional'}): {p.get('description', '')}".strip(": ")
        for p in parameters
        if isinstance(p, dict) and p.get("name")
    ]


def _build_response_lines(responses: dict[str, Any]) -> list[str]:
    return [
        f"{code}: {resp.get('description', '')}"
        for code, resp in responses.items()
        if isinstance(resp, dict)
    ]


def _build_operation_record(
    operation: dict[str, Any],
    method: str,
    path: str,
    spec_url: str,
    api_title: str,
    source_domain: str | None,
    idx: int,
) -> DocPageRecord:
    summary = operation.get("summary", "")
    description = operation.get("description", "")
    tags = operation.get("tags", [])

    title = f"{method.upper()} {path}"
    if summary:
        title = f"{title} — {summary}"

    content_blocks: list[ContentBlock] = []
    if description:
        content_blocks.append({"type": "paragraph", "text": description})
    if tags:
        content_blocks.append({"type": "paragraph", "text": f"Tags: {', '.join(tags)}"})

    param_lines = _build_param_lines(operation.get("parameters", []))
    if param_lines:
        content_blocks.append({"type": "list", "text": "Parameters", "items": param_lines})

    resp_lines = _build_response_lines(operation.get("responses", {}))
    if resp_lines:
        content_blocks.append({"type": "list", "text": "Responses", "items": resp_lines})

    anchor = re.sub(r"[^a-z0-9]+", "-", f"{method}-{path}".lower()).strip("-")
    return {
        "url": f"{spec_url}#{anchor}",
        "canonical_url": f"{spec_url}#{anchor}",
        "depth": 0,
        "order_index": idx,
        "title": title,
        "content_blocks": content_blocks,
        "code_blocks": [],
        "links": [],
        "metadata": {"source_domain": source_domain, "breadcrumbs": [api_title] + tags},
        "errors": [],
    }


# ---------------------------------------------------------------------------
# Shared URL-list fetcher (sitemap and llms.txt link paths)
# ---------------------------------------------------------------------------

def _fetch_one(url: str, idx: int) -> list[DocPageRecord]:
    path_lower = urlparse(url).path.lower()
    if path_lower.endswith((".md", ".markdown")):
        return extract_markdown(url, depth=0, order_index=idx)
    if path_lower.endswith(".pdf"):
        return extract_pdf(url, depth=0, order_index=idx)
    r = _http_get(url, read_limit=PAGE_READ_LIMIT, timeout=PAGE_FETCH_TIMEOUT)
    if r and r["status"] == 200:
        return [extract_from_html(r["body"], url=url, depth=0, order_index=idx)]
    status = r["status"] if r else "connection failed"
    return [make_error_record(url, 0, idx, f"HTTP {status}", None)]


def _is_sparse_record(record: DocPageRecord) -> bool:
    return not record.get("content_blocks") and not record.get("code_blocks")


def _fetch_url_list(
    urls: list[str],
    max_workers: int,
    log: Callable[[str], None],
    include_sparse_pages: bool = False,
) -> list[DocPageRecord]:
    records: list[DocPageRecord] = []
    seen_urls: set[str] = set()
    total = len(urls)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(_fetch_one, url, idx): url
            for idx, url in enumerate(urls)
        }
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                raw_records = future.result()
            except Exception as exc:
                log(f"Adaptive: failed to fetch {url}: {exc}")
                continue
            for raw in raw_records:
                cleaned = clean_record(raw)
                record_url = cleaned.get("url", "")
                if not record_url or record_url in seen_urls:
                    continue
                if not include_sparse_pages and _is_sparse_record(cleaned):
                    log(f"Adaptive: skipping navigation-only page: {record_url}")
                    continue
                seen_urls.add(record_url)
                records.append(cleaned)
                if len(records) % 10 == 0:
                    log(f"Adaptive: fetched {len(records)}/{total} pages...")
    return records


# ---------------------------------------------------------------------------
# Script generation via Ollama (framework path only)
# ---------------------------------------------------------------------------

def _generate_fetch_script(
    state: AgentState, log: Callable[[str], None]
) -> tuple[str | None, str | None]:
    client = _make_llm_client(state.llm_provider)
    if state.llm_provider != "gemini" and client is None:
        return None, _llm_unavailable_reason(state.llm_provider)
    if state.llm_provider == "gemini" and not os.environ.get("GEMINI_API_KEY", "").strip():
        return None, _llm_unavailable_reason(state.llm_provider)

    det = state.detection
    user_prompt = (
        f"Target URL: {state.target_url}\n"
        f"Detection type: {det.type.value if det else 'none'}\n"
        f"Detection URL: {det.url if det else 'n/a'}\n"
        f"Framework: {det.framework if det and det.framework else 'unknown'}\n"
    )
    if state.generation_context:
        user_prompt += f"\nPrevious attempt(s) failed. Error context:\n{state.generation_context}\n"
    user_prompt += "\nWrite the Python extraction script now."

    text = _llm_chat(client, state.llm_provider, state.llm_model, _SCRIPT_SYSTEM, user_prompt, log)
    if not text:
        return None, "empty response from LLM"

    code = re.sub(r"^```(?:python)?\n?", "", text.strip())
    code = re.sub(r"\n?```$", "", code.strip())
    return code.strip(), None


def _make_llm_client(llm_provider: str = DEFAULT_OLLAMA_PROVIDER) -> Any | None:
    provider = _normalize_llm_provider(llm_provider)
    api_key = os.environ.get("OLLAMA_API_KEY", "").strip()
    if provider == "gemini":
        return object()
    if provider == "cloud" and not api_key:
        return None
    try:
        ollama_module = importlib.import_module("ollama")
        client_cls = getattr(ollama_module, "Client", None)
        if client_cls is None:
            return None
        if provider == "local":
            return client_cls(host=os.environ.get("OLLAMA_HOST", LOCAL_OLLAMA_HOST))
        return client_cls(
            host="https://ollama.com",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except Exception:
        return None


def _normalize_llm_provider(llm_provider: str) -> str:
    return llm_provider if llm_provider in {"cloud", "local", "gemini"} else DEFAULT_OLLAMA_PROVIDER


def _llm_unavailable_reason(llm_provider: str) -> str:
    if _normalize_llm_provider(llm_provider) == "gemini":
        return "Gemini not available (missing GEMINI_API_KEY)"
    if _normalize_llm_provider(llm_provider) == "local":
        return "Ollama local server not available (start ollama or install ollama package)"
    return "Ollama cloud not available (missing OLLAMA_API_KEY or ollama package)"


def _llm_chat(
    client: Any,
    llm_provider: str,
    model: str,
    system: str,
    user: str,
    log: Callable[[str], None],
) -> str:
    if llm_provider == "gemini":
        return _gemini_chat(model, system, user, log)
    try:
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=False,
        )
        return _extract_content(response)
    except Exception as exc:
        log(f"Adaptive: LLM call failed: {exc}")
        return ""


def _gemini_chat(
    model: str,
    system: str,
    user: str,
    log: Callable[[str], None],
) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""

    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user}]}],
    }
    timeout_seconds = _resolve_llm_timeout_seconds()
    try:
        response = requests.post(
            f"{GEMINI_API_BASE_URL}/models/{model}:generateContent",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except Exception as exc:
        log(f"Adaptive: Gemini call failed: {exc}")
        return ""
    return _extract_gemini_content(response.json())


def _extract_gemini_content(payload: Any) -> str:
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


def _resolve_llm_timeout_seconds() -> float:
    raw = os.environ.get("DOC_INGESTOR_LLM_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return 90.0
    try:
        value = float(raw)
    except ValueError:
        return 90.0
    return max(5.0, value)


def _extract_content(response: Any) -> str:
    if isinstance(response, dict):
        msg = response.get("message") or {}
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
        content = response.get("content")
        return content if isinstance(content, str) else ""

    msg = getattr(response, "message", None)
    if msg is not None:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]

    content = getattr(response, "content", None)
    return content if isinstance(content, str) else ""


# ---------------------------------------------------------------------------
# Script execution
# ---------------------------------------------------------------------------

def _execute_script(code: str) -> tuple[list[str], str, int]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout_lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        return stdout_lines, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return [], "script timed out after 120s", 1
    except Exception as exc:
        return [], str(exc), 1
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# JSONL → DocPageRecord adapter (script path output)
# ---------------------------------------------------------------------------

def _convert_script_output(lines: list[str]) -> list[DocPageRecord]:
    records: list[DocPageRecord] = []
    for idx, line in enumerate(lines):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = raw.get("content", "")
        content_blocks, code_blocks = _parse_content(content)
        meta = raw.get("metadata") or {}
        record: DocPageRecord = {
            "url": raw.get("url", ""),
            "canonical_url": raw.get("url") or None,
            "depth": int(meta.get("depth", 0)),
            "order_index": idx,
            "title": raw.get("title", f"Page {idx + 1}"),
            "content_blocks": content_blocks,
            "code_blocks": code_blocks,
            "links": [],
            "metadata": {
                "source_domain": urlparse(raw.get("url", "")).netloc or None,
                "breadcrumbs": [],
            },
            "errors": [],
        }
        records.append(record)
    return records


def _parse_content(text: str) -> tuple[list[ContentBlock], list[CodeBlock]]:
    content_blocks: list[ContentBlock] = []
    code_blocks: list[CodeBlock] = []
    last = 0
    for match in re.finditer(r"```(\w+)?\n(.*?)```", text, re.DOTALL):
        prose = text[last : match.start()].strip()
        if prose:
            content_blocks.append({"type": "paragraph", "text": prose})
        code_blocks.append({"language": match.group(1) or None, "text": match.group(2).strip()})
        last = match.end()
    remaining = text[last:].strip()
    if remaining:
        content_blocks.append({"type": "paragraph", "text": remaining})
    return content_blocks, code_blocks


# ---------------------------------------------------------------------------
# Quality evaluation (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _evaluate_quality(records: list[DocPageRecord]) -> dict[str, Any]:
    if not records:
        return {"structural": 0.0, "density": 0.0, "scope": 0.0, "passed": False}

    word_counts = [_word_count(r) for r in records]
    valid = sum(
        1 for r, wc in zip(records, word_counts)
        if r.get("url") and r.get("title") and wc > 10
    )
    structural = valid / len(records)
    density = min(sum(word_counts) / len(records) / 1500.0, 1.0)
    scope = min(len(records) / 5.0, 1.0)
    passed = structural > 0.95 and density > 0.15 and scope >= 1.0
    return {"structural": structural, "density": density, "scope": scope, "passed": passed}


def _word_count(record: DocPageRecord) -> int:
    count = 0
    for block in record.get("content_blocks") or []:
        count += len((block.get("text") or "").split())
        for item in block.get("items") or []:
            count += len(item.split())
    for block in record.get("code_blocks") or []:
        count += len((block.get("text") or "").split())
    return count


def _is_complete_single_document(records: list[DocPageRecord], metrics: dict[str, Any]) -> bool:
    if len(records) != 1:
        return False
    if metrics.get("structural", 0.0) < 0.95:
        return False
    return _word_count(records[0]) >= 1200


def _is_unproductive_crawler_retry(state: AgentState) -> bool:
    return (
        state.detection is None
        and state.retry_count > 0
        and len(state.doc_records) <= 1
        and state.crawler_kwargs.get("include_sparse_pages")
        and state.crawler_kwargs.get("max_depth") is None
    )


# ---------------------------------------------------------------------------
# Self-correction
# ---------------------------------------------------------------------------

def _self_correct(state: AgentState, log: Callable[[str], None]) -> None:
    is_script_path = (
        state.detection is not None
        and state.detection.type == DetectionType.FRAMEWORK
    )
    if is_script_path:
        context_parts: list[str] = []
        if state.script_returncode not in (None, 0):
            context_parts.append(f"Exit code: {state.script_returncode}")
        if state.script_stderr:
            trimmed = "\n".join(state.script_stderr.splitlines()[-20:])
            context_parts.append(f"Stderr (last 20 lines):\n{trimmed}")
        m = state.eval_metrics
        context_parts.append(
            f"Quality: structural={m.get('structural', 0):.2f}, "
            f"density={m.get('density', 0):.2f}, "
            f"scope={m.get('scope', 0):.2f}"
        )
        new_context = "\n".join(context_parts)
        state.generation_context = (
            f"{state.generation_context}\n\n--- Retry {state.retry_count} ---\n{new_context}"
            if state.generation_context
            else new_context
        )
        log("Adaptive: rewriting script with accumulated error context...")
        state.phase = CrawlerPhase.GENERATE_SCRIPT
    elif state.detection is not None and state.detection.type == DetectionType.SITEMAP:
        log("Adaptive: sitemap produced low-quality metrics, falling back to crawler...")
        state.detection = None
        state.doc_records = []
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
    elif state.detection is not None:
        # Structured source (sitemap/llms.txt/openapi) was found — accept results as-is
        # rather than falling back to BFS, which would re-crawl the same site differently.
        log("Adaptive: structured source produced low-quality metrics, accepting results as-is...")
        state.phase = CrawlerPhase.DONE
    else:
        # No structured endpoint found — BFS is the only option; tune its parameters.
        if not state.crawler_kwargs.get("include_sparse_pages"):
            state.crawler_kwargs["include_sparse_pages"] = True
            log("Adaptive: retrying crawler with include_sparse_pages=True...")
        elif state.crawler_kwargs.get("max_depth") is not None:
            state.crawler_kwargs["max_depth"] = None
            log("Adaptive: retrying crawler with no depth limit...")
        else:
            log("Adaptive: no further crawler adjustments available, retrying as-is...")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK


# ---------------------------------------------------------------------------
# Feedback agent (XAI report)
# ---------------------------------------------------------------------------

def _generate_feedback(
    state: AgentState, log: Callable[[str], None]
) -> dict[str, Any] | None:
    client = _make_llm_client(state.llm_provider)
    if state.llm_provider != "gemini" and client is None:
        log("Adaptive: feedback analysis skipped (LLM not available)")
        return None
    if state.llm_provider == "gemini" and not os.environ.get("GEMINI_API_KEY", "").strip():
        log("Adaptive: feedback analysis skipped (Gemini not available)")
        return None

    text = _llm_chat(client, state.llm_provider, state.llm_model, _FEEDBACK_SYSTEM, _build_trace(state), log)
    if not text:
        return None

    cleaned = re.sub(r"^```(?:json)?\n?", "", text.strip())
    cleaned = re.sub(r"\n?```$", "", cleaned.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log(f"Adaptive: feedback JSON parse failed: {cleaned[:200]}")
        return None


def _build_trace(state: AgentState) -> str:
    parts = [f"Target URL: {state.target_url}"]
    if state.detection:
        parts.append(
            f"Detection: {state.detection.type.value} "
            f"({state.detection.framework or 'n/a'}) at {state.detection.url}"
        )
    if state.generated_code:
        parts.append(f"Script ({len(state.generated_code)} chars):\n{state.generated_code[:1000]}")
    if state.script_stderr:
        parts.append(f"Script stderr:\n{state.script_stderr[-1000:]}")
    if state.script_returncode is not None:
        parts.append(f"Script exit code: {state.script_returncode}")
    m = state.eval_metrics
    if m:
        parts.append(
            f"Quality: structural={m.get('structural', 0):.2f}, "
            f"density={m.get('density', 0):.2f}, "
            f"scope={m.get('scope', 0):.2f}"
        )
    parts.append(f"Records produced: {len(state.doc_records)}")
    parts.append(f"Retries attempted: {state.retry_count}")
    return "\n".join(parts)


def _emit_feedback_report(report: dict[str, Any], log: Callable[[str], None]) -> None:
    log("Adaptive feedback report:")
    log(f"  failure_mode:              {report.get('failure_mode', 'unknown')}")
    log(f"  confidence_score:          {report.get('confidence_score', 0):.2f}")
    log(f"  permanent_fix_recommended: {report.get('permanent_fix_recommended', False)}")
    log(f"  rationale:                 {report.get('rationale', '')}")
    log(f"  immediate_fix:             {report.get('immediate_fix', '')}")


def _stderr_logger(message: str) -> None:
    print(message, file=sys.stderr)
