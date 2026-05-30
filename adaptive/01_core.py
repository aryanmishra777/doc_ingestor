"""Adaptive crawler constants, prompts, and core state enums.

This module defines the stable values shared by the adaptive state machine: timeout
settings, provider defaults, prompt templates, detection types, crawler phases, and the
small result objects passed between phase handlers.
"""
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
