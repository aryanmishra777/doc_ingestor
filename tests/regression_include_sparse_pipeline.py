"""Include-sparse feature: pipeline record processing, signatures, and CLI flag."""
from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

from regression_sparse_fixtures import RICH_HTML, nav_only_record
from regression_util import Checker

from extraction import extract_from_html
from pipeline import _process_raw_record, collect_records, run_pipeline, run_pipeline_result

c = Checker("Include-sparse pipeline behaviour")

rich = extract_from_html(RICH_HTML, url="https://example.com/docs/col")

# --- Section 4: _process_raw_record — default mode skips nav-only ---
logs: list[str] = []
records: list = []
seen_canonical: set = set()
seen_hashes: set = set()

accepted, _, _ = _process_raw_record(
    nav_only_record(), "https://example.com/nav",
    logs.append, records, seen_canonical, seen_hashes, 0, 0,
    include_sparse_pages=False,
)
c.check("default mode: nav-only record is rejected", not accepted)
c.check("default mode: rejection logged", any("discovery, not output" in m for m in logs))
c.check("default mode: records list unchanged", len(records) == 0)

logs.clear()
accepted, _, _ = _process_raw_record(
    rich, "https://example.com/docs/col",
    logs.append, records, seen_canonical, seen_hashes, 0, 0,
    include_sparse_pages=False,
)
c.check("default mode: rich record is accepted", accepted)
c.check("default mode: rich record appended", len(records) == 1)

# --- Section 5: _process_raw_record — include_sparse_pages=True ---
logs2: list[str] = []
records2: list = []
seen_canonical2: set = set()
seen_hashes2: set = set()

accepted2, _, _ = _process_raw_record(
    nav_only_record(), "https://example.com/nav",
    logs2.append, records2, seen_canonical2, seen_hashes2, 0, 0,
    include_sparse_pages=True,
)
c.check("include_sparse mode: nav-only record is accepted", accepted2)
c.check("include_sparse mode: acceptance logged", any("--include-sparse" in m for m in logs2))
c.check("include_sparse mode: record appended", len(records2) == 1)

logs2.clear()
accepted3, _, _ = _process_raw_record(
    rich, "https://example.com/docs/col",
    logs2.append, records2, seen_canonical2, seen_hashes2, 0, 0,
    include_sparse_pages=True,
)
c.check("include_sparse mode: rich record still accepted", accepted3)
c.check("include_sparse mode: records now has 2", len(records2) == 2)

# --- Section 6: function signatures accept include_sparse_pages ---
from cli import collect_records_for_seeds, write_outputs_per_seed, _collect_seed_records

for fn_name, fn in [
    ("run_pipeline", run_pipeline),
    ("run_pipeline_result", run_pipeline_result),
    ("collect_records", collect_records),
    ("collect_records_for_seeds", collect_records_for_seeds),
    ("write_outputs_per_seed", write_outputs_per_seed),
    ("_collect_seed_records", _collect_seed_records),
]:
    params = inspect.signature(fn).parameters
    c.check(f"{fn_name} has include_sparse_pages param", "include_sparse_pages" in params)

# --- Section 7: CLI --help includes the flag ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(
    [sys.executable, "-m", "doc_ingestor.cli", "--help"],
    capture_output=True,
    text=True,
    cwd=str(PROJECT_ROOT),
)
if result.returncode != 0:
    result = subprocess.run(
        [sys.executable, "cli.py", "--help"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
c.check("--help exits 0", result.returncode == 0, f"rc={result.returncode}")
c.check(
    "--include-sparse appears in --help",
    "--include-sparse" in result.stdout,
    result.stdout[:300] if "--include-sparse" not in result.stdout else "",
)

c.finish()
