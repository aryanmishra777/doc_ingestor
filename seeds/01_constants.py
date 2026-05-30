"""Seed discovery imports, constants, prompts, and diagnostics.

Defines the URL hints, probing limits, provider defaults, search configuration, and the
diagnostics object shared by every seed-discovery strategy.
"""
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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

import requests

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
DEFAULT_OLLAMA_PROVIDER = "cloud"
DEFAULT_CLOUD_LLM_SEED_MODEL = "gemma4:31b-cloud"
DEFAULT_LOCAL_LLM_SEED_MODEL = "gemma4:latest"
DEFAULT_GEMINI_LLM_SEED_MODEL = "gemini-2.5-flash-lite"
DEFAULT_LLM_SEED_MODEL = DEFAULT_CLOUD_LLM_SEED_MODEL
LOCAL_OLLAMA_HOST = "http://localhost:11434"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_LLM_CONTEXT_LINKS = 60
WEB_SEARCH_TIMEOUT_SECONDS = 8.0
DEFAULT_LLM_TIMEOUT_SECONDS = 90.0
DEFAULT_WEB_SEARCH_PROVIDER = "auto"
SEARXNG_SEARCH_URL_SUFFIX = "/search"
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
