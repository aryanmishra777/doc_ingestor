"""CLI imports and stable defaults.

Keeps the command-line entry point import-compatible in both package and script execution
modes, then exposes the default start URL used when no positional URL is supplied.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

if __package__:
    from .adaptive import (
        DEFAULT_ADAPTIVE_MODEL,
        DEFAULT_CLOUD_ADAPTIVE_MODEL,
        DEFAULT_GEMINI_ADAPTIVE_MODEL,
        DEFAULT_LOCAL_ADAPTIVE_MODEL,
        collect_records_adaptive,
    )
    from .models import DocPageRecord
    from .pipeline import DEFAULT_CHUNK_PAGES, collect_records, write_markdown_outputs
    from .seeds import (
        DEFAULT_CLOUD_LLM_SEED_MODEL,
        DEFAULT_GEMINI_LLM_SEED_MODEL,
        DEFAULT_LLM_SEED_MODEL,
        DEFAULT_LOCAL_LLM_SEED_MODEL,
        SeedDiscoveryDiagnostics,
        discover_seed_urls_with_diagnostics,
    )
    from .structuring import structure_records_to_markdown
else:
    sys.path.append(str(Path(__file__).resolve().parent))
    from adaptive import (
        DEFAULT_ADAPTIVE_MODEL,
        DEFAULT_CLOUD_ADAPTIVE_MODEL,
        DEFAULT_GEMINI_ADAPTIVE_MODEL,
        DEFAULT_LOCAL_ADAPTIVE_MODEL,
        collect_records_adaptive,
    )
    from models import DocPageRecord
    from pipeline import DEFAULT_CHUNK_PAGES, collect_records, write_markdown_outputs
    from seeds import (
        DEFAULT_CLOUD_LLM_SEED_MODEL,
        DEFAULT_GEMINI_LLM_SEED_MODEL,
        DEFAULT_LLM_SEED_MODEL,
        DEFAULT_LOCAL_LLM_SEED_MODEL,
        SeedDiscoveryDiagnostics,
        discover_seed_urls_with_diagnostics,
    )
    from structuring import structure_records_to_markdown


DEFAULT_START_URL = "https://example.com/docs"
