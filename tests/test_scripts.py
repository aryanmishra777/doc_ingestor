"""Pytest bridge for the repository's script-style regression tests."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_TESTS = [
    "regression_adaptive_llms.py",
    "regression_adaptive_llms_parse.py",
    "regression_adaptive_single_doc.py",
    "regression_adaptive_sitemap.py",
    "regression_adaptive_sitemap_roots.py",
    "regression_adaptive_sitemap_helpers.py",
    "regression_gemini_integration.py",
    "regression_seed_filtering.py",
    "regression_seed_web_search.py",
    "regression_seed_web_search_ddg.py",
    "regression_include_sparse.py",
    "regression_include_sparse_pipeline.py",
]


def test_script_regressions() -> None:
    """Run each standalone regression script with the current Python interpreter."""
    for script in SCRIPT_TESTS:
        result = subprocess.run(
            [sys.executable, str(Path("tests") / script)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
