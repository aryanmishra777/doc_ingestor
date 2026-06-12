"""Validation for feedback-analysis agent reports.

The feedback agent returns free-form JSON from an LLM. Before the state machine acts on
it, the report is normalized against this closed schema: an unknown failure mode rejects
the whole report, so LLM output can steer — but never break — the deterministic
self-correction logic.
"""
from __future__ import annotations

from typing import Any

#: Closed set of diagnosable failure modes; must match the modes in ``_FEEDBACK_SYSTEM``.
FAILURE_MODES = frozenset(
    {
        "SELECTOR_MISMATCH",
        "PAGINATION_FAILURE",
        "RATE_LIMITED",
        "EMPTY_CONTENT",
        "SYNTAX_ERROR",
        "JS_NOT_RENDERED",
        "ANTIBOT",
        "AUTH_REQUIRED",
        "INFINITE_SCROLL",
    }
)


def validate_feedback_report(raw: Any) -> dict[str, Any] | None:
    """Normalize a parsed feedback report, or return ``None`` if it is unusable."""
    if not isinstance(raw, dict):
        return None
    mode = str(raw.get("failure_mode", "")).strip().upper()
    if mode not in FAILURE_MODES:
        return None
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence_score", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "failure_mode": mode,
        "confidence_score": confidence,
        "permanent_fix_recommended": bool(raw.get("permanent_fix_recommended", False)),
        "rationale": str(raw.get("rationale", "")),
        "immediate_fix": str(raw.get("immediate_fix", "")),
    }
