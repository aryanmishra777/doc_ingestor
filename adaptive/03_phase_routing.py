

"""Phase routing, fallback, and initial API detection.

Contains the phase dispatch table plus the handlers that evaluate output, trigger
feedback analysis, fall back to the standard crawler, and detect llms.txt/sitemap
sources during probing.
"""

def _phase_crawler_fallback(state: AgentState, log: Callable[[str], None]) -> None:
    log("Adaptive: running standard crawler...")
    try:
        records, _ = collect_records(state.target_url, **state.crawler_kwargs)
        state.doc_records = records
        log(f"Adaptive: crawler produced {len(records)} records")
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        log(f"Adaptive: crawler failed: {exc}")
        state.doc_records = []
    state.phase = CrawlerPhase.EVALUATE_QUALITY


def _phase_evaluate_quality(state: AgentState, log: Callable[[str], None]) -> None:
    state.eval_metrics = _evaluate_quality(state.doc_records)
    log(
        "Adaptive: quality — "
        f"structural={state.eval_metrics['structural']:.2f}, "
        f"density={state.eval_metrics['density']:.2f}, "
        f"scope={state.eval_metrics['scope']:.2f}, "
        f"passed={state.eval_metrics['passed']}"
    )
    if state.eval_metrics["passed"]:
        state.phase = CrawlerPhase.DONE
    elif _is_complete_single_document(state.doc_records, state.eval_metrics):
        log("Adaptive: accepting dense single-document output despite low multi-page scope")
        state.phase = CrawlerPhase.DONE
    elif _is_unproductive_crawler_retry(state):
        log("Adaptive: crawler retry did not broaden output, accepting current records")
        state.phase = CrawlerPhase.DONE if state.doc_records else CrawlerPhase.FAILED
    elif state.retry_count < MAX_RETRIES:
        state.retry_count += 1
        log(f"Adaptive: self-correcting (attempt {state.retry_count}/{MAX_RETRIES})...")
        state.phase = CrawlerPhase.SELF_CORRECT
    else:
        log("Adaptive: retry budget exhausted, generating feedback report...")
        state.phase = CrawlerPhase.FEEDBACK_ANALYSIS


def _phase_feedback_analysis(state: AgentState, log: Callable[[str], None]) -> None:
    log("Adaptive: generating XAI feedback report...")
    state.feedback_report = _generate_feedback(state, log)
    if state.feedback_report:
        _emit_feedback_report(state.feedback_report, log)
    state.phase = CrawlerPhase.DONE if state.doc_records else CrawlerPhase.FAILED


_PHASE_DISPATCH: dict[CrawlerPhase, Callable[[AgentState, Callable[[str], None]], None]] = {
    CrawlerPhase.INIT: _phase_init,
    CrawlerPhase.PROBE_API: _phase_probe_api,
    CrawlerPhase.FETCH_LLMS_TXT: _phase_fetch_llms_txt,
    CrawlerPhase.FETCH_SITEMAP: _phase_fetch_sitemap,
    CrawlerPhase.CONVERT_OPENAPI: _phase_convert_openapi,
    CrawlerPhase.GENERATE_SCRIPT: _phase_generate_script,
    CrawlerPhase.EXECUTE_SCRIPT: _phase_execute_script,
    CrawlerPhase.CRAWLER_FALLBACK: _phase_crawler_fallback,
    CrawlerPhase.EVALUATE_QUALITY: _phase_evaluate_quality,
    CrawlerPhase.SELF_CORRECT: lambda s, l: _self_correct(s, l),
    CrawlerPhase.FEEDBACK_ANALYSIS: _phase_feedback_analysis,
}


def _run_phase(state: AgentState, log: Callable[[str], None]) -> None:
    handler = _PHASE_DISPATCH.get(state.phase)
    if handler is not None:
        handler(state, log)


# ---------------------------------------------------------------------------
# Pre-checks: parallel HTTP probes
# ---------------------------------------------------------------------------

def _detect_llms_txt(
    responses: dict[str, dict[str, Any] | None],
    probe_paths: dict[str, str],
    base: str,
) -> DetectionResult | None:
    for key in ("llms_full_1", "llms_full_2", "llms_1", "llms_2"):
        r = responses.get(key)
        if not r or r["status"] != 200:
            continue
        ct = r["content_type"].lower()
        if "text/plain" in ct or "text/markdown" in ct or "markdown" in ct:
            return DetectionResult(
                type=DetectionType.LLMS_TXT,
                url=base + probe_paths[key],
                prefetched_content=r["body"],
            )
    return None


def _detect_sitemap(
    responses: dict[str, dict[str, Any] | None],
    probe_paths: dict[str, str],
    base: str,
) -> DetectionResult | None:
    for key in ("sitemap_1", "sitemap_2"):
        r = responses.get(key)
        if not r or r["status"] != 200:
            continue
        body = r["body"]
        if "<urlset" in body or "<sitemapindex" in body:
            return DetectionResult(
                type=DetectionType.SITEMAP,
                url=base + probe_paths[key],
                prefetched_content=body,
            )
    return None
