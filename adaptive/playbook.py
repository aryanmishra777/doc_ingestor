"""Cross-run adaptive memory: the playbook.

Every finished adaptive run appends one JSONL entry (domain, strategy, quality, failure
mode, and the generated script when it worked). Later runs consult it to skip strategies
that repeatedly failed for a domain and to reuse fetch scripts that already succeeded —
this is what makes the agent adaptive *across* runs, not just within one.

Storage defaults to ``~/.doc_ingestor/playbook.jsonl``; the ``DOC_INGESTOR_PLAYBOOK``
env var overrides the path or disables the playbook entirely (``0``/``off``). Every
function here swallows I/O errors: memory must never break a crawl.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_MAX_STORED_SCRIPT_CHARS = 20000
_SKIP_AFTER_FAILURES = 2


def playbook_path() -> Path | None:
    raw = os.environ.get("DOC_INGESTOR_PLAYBOOK", "").strip()
    if raw.lower() in {"0", "off", "disabled", "none"}:
        return None
    if raw and raw.lower() not in {"1", "on"}:
        return Path(raw)
    return Path.home() / ".doc_ingestor" / "playbook.jsonl"


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def record_outcome(state: Any, succeeded: bool) -> None:
    """Append one playbook entry for a finished adaptive run. Never raises."""
    path = playbook_path()
    if path is None:
        return
    detection = getattr(state, "detection", None)
    strategy = detection.type.value if detection else "crawler"
    entry: dict[str, Any] = {
        "ts": time.time(),
        "domain": domain_of(state.target_url),
        "strategy": strategy,
        "framework": detection.framework if detection else None,
        "succeeded": bool(succeeded),
        "metrics": {
            k: state.eval_metrics.get(k) for k in ("structural", "density", "scope", "passed")
        },
        "records": len(state.doc_records),
        "retries": state.retry_count,
        "failure_mode": (state.feedback_report or {}).get("failure_mode"),
    }
    if succeeded and strategy == "framework" and state.generated_code:
        entry["script"] = state.generated_code[:_MAX_STORED_SCRIPT_CHARS]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def entries_for_domain(domain: str) -> list[dict[str, Any]]:
    path = playbook_path()
    if path is None:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    entries: list[dict[str, Any]] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and entry.get("domain") == domain:
            entries.append(entry)
    return entries


def cached_script(domain: str, framework: str | None) -> str | None:
    """Return the most recent fetch script that succeeded for this domain+framework."""
    for entry in reversed(entries_for_domain(domain)):
        if (
            entry.get("succeeded")
            and entry.get("script")
            and entry.get("framework") == framework
        ):
            return str(entry["script"])
    return None


def should_skip_detection(domain: str, detection_type: str) -> bool:
    """True when this strategy keeps failing here and the plain crawler has succeeded."""
    failures = 0
    crawler_succeeded = False
    for entry in entries_for_domain(domain):
        if entry.get("strategy") == detection_type and not entry.get("succeeded"):
            failures += 1
        if entry.get("strategy") == detection_type and entry.get("succeeded"):
            failures = 0  # a later success resets the verdict
        if entry.get("strategy") == "crawler" and entry.get("succeeded"):
            crawler_succeeded = True
    return failures >= _SKIP_AFTER_FAILURES and crawler_succeeded
