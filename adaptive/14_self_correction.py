

"""Self-correction strategy selection.

Consumes the validated feedback report produced by the diagnosis phase: the failure mode
picks the next corrective action from a fixed whitelist (the LLM proposes, this code
disposes). When no report is available — LLM absent, parse failure, schema rejection, or
a structured source where re-fetching cannot help — the original deterministic retry
ladder applies, so behaviour degrades gracefully to the pre-feedback design.
"""

_SCRIPT_FIX_HINTS: dict[str, str | None] = {
    # None means: use the report's own immediate_fix/rationale text.
    "SELECTOR_MISMATCH": None,
    "PAGINATION_FAILURE": None,
    "SYNTAX_ERROR": None,
    "RATE_LIMITED": (
        "The target rate-limits requests: add a delay of at least 1 second between "
        "requests and retry failed requests once with backoff."
    ),
    "JS_NOT_RENDERED": (
        "The page content is rendered by JavaScript, so raw HTML scraping returns "
        "shells: locate the framework's data endpoints (JSON payloads, search index) "
        "and fetch those instead."
    ),
    "EMPTY_CONTENT": (
        "Previous selectors matched nothing: derive selectors from the actual markup "
        "and fall back to extracting all <main> or <article> text."
    ),
    "INFINITE_SCROLL": (
        "Content loads via infinite scroll: find the underlying paginated API the page "
        "calls instead of scraping the rendered HTML."
    ),
}


def _self_correct(state: AgentState, log: Callable[[str], None]) -> None:
    if _correct_from_feedback(state, log):
        return
    _ladder_correct(state, log)


def _correct_from_feedback(state: AgentState, log: Callable[[str], None]) -> bool:
    report = state.feedback_report
    if not report:
        return False
    mode = report.get("failure_mode", "")
    if state.detection is not None and state.detection.type == DetectionType.FRAMEWORK:
        return _correct_script_path(state, log, mode, report)
    if state.detection is None:
        return _correct_crawler_path(state, log, mode)
    # Structured sources (llms.txt/sitemap/openapi): re-fetching the same endpoint
    # cannot change its content, so keep the ladder's fallback/accept semantics.
    return False


def _correct_script_path(
    state: AgentState, log: Callable[[str], None], mode: str, report: dict[str, Any]
) -> bool:
    if mode not in _SCRIPT_FIX_HINTS:
        # ANTIBOT / AUTH_REQUIRED — no automated script fix exists; let the ladder run.
        return False
    hint = _SCRIPT_FIX_HINTS[mode] or report.get("immediate_fix") or report.get("rationale") or ""
    _append_generation_context(state, f"Diagnosed failure mode: {mode}. {hint}")
    if state.script_stderr:
        trimmed = "\n".join(state.script_stderr.splitlines()[-20:])
        _append_generation_context(state, f"Stderr (last 20 lines):\n{trimmed}")
    log(f"Adaptive: rewriting script for diagnosed {mode}...")
    state.phase = CrawlerPhase.GENERATE_SCRIPT
    return True


def _correct_crawler_path(state: AgentState, log: Callable[[str], None], mode: str) -> bool:
    if mode == "RATE_LIMITED":
        state.crawler_kwargs["max_workers"] = 1
        log("Adaptive: diagnosed rate limiting, retrying crawler with a single worker...")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return True
    if mode in {"EMPTY_CONTENT", "JS_NOT_RENDERED"} and not state.crawler_kwargs.get("include_sparse_pages"):
        state.crawler_kwargs["include_sparse_pages"] = True
        log(f"Adaptive: diagnosed {mode}, retrying crawler with include_sparse_pages=True...")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
        return True
    return False


def _append_generation_context(state: AgentState, text: str) -> None:
    marker = f"--- Retry {state.retry_count} ---"
    if state.generation_context:
        state.generation_context = f"{state.generation_context}\n\n{marker}\n{text}"
    else:
        state.generation_context = f"{marker}\n{text}"


def _ladder_correct(state: AgentState, log: Callable[[str], None]) -> None:
    is_script_path = (
        state.detection is not None
        and state.detection.type == DetectionType.FRAMEWORK
    )
    if is_script_path:
        context_parts: list[str] = []
        if state.script_returncode not in (None, 0):
            context_parts.append(f"Exit code: {state.script_returncode}")
        if state.script_stderr:
            trimmed = "\n".join(state.script_stderr.splitlines()[-20:])
            context_parts.append(f"Stderr (last 20 lines):\n{trimmed}")
        m = state.eval_metrics
        context_parts.append(
            f"Quality: structural={m.get('structural', 0):.2f}, "
            f"density={m.get('density', 0):.2f}, "
            f"scope={m.get('scope', 0):.2f}"
        )
        new_context = "\n".join(context_parts)
        state.generation_context = (
            f"{state.generation_context}\n\n--- Retry {state.retry_count} ---\n{new_context}"
            if state.generation_context
            else new_context
        )
        log("Adaptive: rewriting script with accumulated error context...")
        state.phase = CrawlerPhase.GENERATE_SCRIPT
    elif state.detection is not None and state.detection.type == DetectionType.SITEMAP:
        log("Adaptive: sitemap produced low-quality metrics, falling back to crawler...")
        state.detection = None
        state.doc_records = []
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
    elif state.detection is not None:
        # Structured source (llms.txt/openapi) was found — accept results as-is
        # rather than falling back to BFS, which would re-crawl the same site differently.
        log("Adaptive: structured source produced low-quality metrics, accepting results as-is...")
        state.phase = CrawlerPhase.DONE
    else:
        # No structured endpoint found — BFS is the only option; tune its parameters.
        if not state.crawler_kwargs.get("include_sparse_pages"):
            state.crawler_kwargs["include_sparse_pages"] = True
            log("Adaptive: retrying crawler with include_sparse_pages=True...")
        elif state.crawler_kwargs.get("max_depth") is not None:
            state.crawler_kwargs["max_depth"] = None
            log("Adaptive: retrying crawler with no depth limit...")
        else:
            log("Adaptive: no further crawler adjustments available, retrying as-is...")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK
