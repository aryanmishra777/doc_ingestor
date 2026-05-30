

# ---------------------------------------------------------------------------
# Feedback agent (XAI report)
# ---------------------------------------------------------------------------

"""Feedback report generation for failed adaptive attempts.

Builds a compact trace of adaptive decisions, asks the LLM for failure analysis when
available, emits the report, and provides the default stderr logger.
"""

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
