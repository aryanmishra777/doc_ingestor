"""Tool factories for the adaptive feedback-analysis agent."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


def feedback_analysis_tools(state: Any, trace: str) -> list[Callable[[], str]]:
    """Build LangChain tools that expose execution evidence to the feedback agent."""
    return [
        _execution_trace_tool(trace),
        _quality_metrics_tool(state),
        _retry_history_tool(state),
    ]


def _execution_trace_tool(trace: str) -> Callable[[], str]:
    def execution_trace() -> str:
        """Read the full adaptive execution trace for this failed crawl."""
        return trace

    return execution_trace


def _quality_metrics_tool(state: Any) -> Callable[[], str]:
    def quality_metrics() -> str:
        """Read deterministic quality scores from the last adaptive attempt."""
        metrics = state.eval_metrics or {}
        return (
            f"structural={metrics.get('structural', 0):.2f}\n"
            f"density={metrics.get('density', 0):.2f}\n"
            f"scope={metrics.get('scope', 0):.2f}\n"
            f"records={len(state.doc_records)}"
        )

    return quality_metrics


def _retry_history_tool(state: Any) -> Callable[[], str]:
    def retry_history() -> str:
        """Read retry count, generated script status, and stderr summary."""
        return (
            f"retry_count={state.retry_count}\n"
            f"script_returncode={state.script_returncode}\n"
            f"generation_context={state.generation_context or 'n/a'}\n"
            f"stderr_tail={state.script_stderr[-1000:] if state.script_stderr else 'n/a'}"
        )

    return retry_history
