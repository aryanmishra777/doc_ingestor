

"""Opt-in LLM-as-judge quality spot check.

The deterministic metrics count words, so they cannot tell clean documentation prose
from navigation boilerplate that happens to be long. When ``DOC_INGESTOR_LLM_JUDGE`` is
enabled, a run that passes the deterministic checks is additionally spot-checked: up to
three sampled records go to the configured model, and a majority JUNK verdict demotes
the pass so self-correction still runs. Cheap with a local Ollama model; off by default
so no behaviour changes without explicit opt-in.
"""

_JUDGE_SYSTEM = """\
You are a documentation quality auditor. For each numbered excerpt decide whether it is
substantive documentation content (CLEAN) or navigation menus, link lists, cookie/legal
boilerplate, or other junk (JUNK). Respond with exactly one line per excerpt in the form
`<number>: CLEAN` or `<number>: JUNK` and nothing else.
"""

_JUDGE_EXCERPT_CHARS = 500


def _llm_judge_enabled() -> bool:
    return os.environ.get("DOC_INGESTOR_LLM_JUDGE", "").strip().lower() in {"1", "true", "yes", "on"}


def _judge_sample_records(state: AgentState, log: Callable[[str], None]) -> float | None:
    """Return the fraction of sampled records judged CLEAN, or None when unavailable."""
    if not state.doc_records:
        return None
    client = _make_llm_client(state.llm_provider)
    if state.llm_provider != "gemini" and client is None:
        return None
    if state.llm_provider == "gemini" and not os.environ.get("GEMINI_API_KEY", "").strip():
        return None

    records = state.doc_records
    indices = sorted({0, len(records) // 2, len(records) - 1})
    prompt_parts = [
        f"{n}. Title: {records[i].get('title') or '(untitled)'}\n{_record_excerpt(records[i])}"
        for n, i in enumerate(indices, start=1)
    ]
    text = _llm_chat(
        client, state.llm_provider, state.llm_model,
        _JUDGE_SYSTEM, "\n\n".join(prompt_parts), log,
    )
    verdicts = re.findall(r"\b(CLEAN|JUNK)\b", text.upper())
    if not verdicts:
        return None
    return verdicts.count("CLEAN") / len(verdicts)


def _record_excerpt(record: DocPageRecord) -> str:
    parts: list[str] = []
    for block in record.get("content_blocks") or []:
        text = block.get("text") or ""
        if text:
            parts.append(text)
        if sum(len(p) for p in parts) >= _JUDGE_EXCERPT_CHARS:
            break
    return " ".join(parts)[:_JUDGE_EXCERPT_CHARS]


def _apply_llm_judge(state: AgentState, log: Callable[[str], None]) -> None:
    """Demote a deterministic pass when sampled records look like junk."""
    if not state.eval_metrics.get("passed") or not _llm_judge_enabled():
        return
    score = _judge_sample_records(state, log)
    if score is None:
        return
    state.eval_metrics["judge"] = score
    if score < 0.5:
        state.eval_metrics["passed"] = False
        log(f"Adaptive: LLM judge flagged sampled records as junk (clean fraction={score:.2f})")