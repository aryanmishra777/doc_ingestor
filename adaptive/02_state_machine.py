

"""Primary adaptive state machine and phase entry points.

Owns :class:`AgentState`, the public :func:`collect_records_adaptive`, and the thin phase
handlers that advance the crawl through probing, fetching, script generation, execution,
and fallback.
"""

from adaptive.playbook import cached_script, domain_of, record_outcome, should_skip_detection

@dataclass
class AgentState:
    target_url: str
    llm_model: str = DEFAULT_ADAPTIVE_MODEL
    llm_provider: str = DEFAULT_OLLAMA_PROVIDER
    phase: CrawlerPhase = CrawlerPhase.INIT
    detection: DetectionResult | None = None
    crawl_seed_urls: list[str] = field(default_factory=list)
    generated_code: str | None = None
    script_stdout: list[str] = field(default_factory=list)
    script_stderr: str = ""
    script_returncode: int | None = None
    generation_context: str = ""
    doc_records: list[DocPageRecord] = field(default_factory=list)
    crawler_kwargs: dict[str, Any] = field(default_factory=dict)
    eval_metrics: dict[str, Any] = field(default_factory=dict)
    feedback_report: dict[str, Any] | None = None
    retry_count: int = 0
    retries_exhausted: bool = False


def collect_records_adaptive(
    start_url: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    logger: Callable[[str], None] | None = None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
    llm_model: str = DEFAULT_ADAPTIVE_MODEL,
    llm_provider: str = DEFAULT_OLLAMA_PROVIDER,
) -> tuple[list[DocPageRecord], PipelineStats]:
    log = logger or _stderr_logger
    state = AgentState(
        target_url=start_url,
        llm_model=llm_model,
        llm_provider=llm_provider,
        crawler_kwargs={
            "max_pages": max_pages,
            "max_depth": max_depth,
            "max_workers": max_workers,
            "include_sparse_pages": include_sparse_pages,
            "logger": log,
        },
    )
    _terminal = {CrawlerPhase.DONE, CrawlerPhase.FAILED}
    while state.phase not in _terminal:
        _run_phase(state, log)

    record_outcome(
        state,
        succeeded=(
            state.phase == CrawlerPhase.DONE
            and bool(state.doc_records)
            and bool(state.eval_metrics.get("passed"))
        ),
    )
    required_depth = max((r.get("depth") or 0) for r in state.doc_records) if state.doc_records else 0
    stats = PipelineStats(
        pages=len(state.doc_records),
        required_depth=required_depth,
        failed_pages=0,
        truncated_by_page_cap=False,
        depth_cap_reached=False,
    )
    return state.doc_records, stats


# ---------------------------------------------------------------------------
# Phase handler functions (one per CrawlerPhase)
# ---------------------------------------------------------------------------

def _phase_init(state: AgentState) -> None:
    state.phase = CrawlerPhase.PROBE_API


def _phase_probe_api(state: AgentState, log: Callable[[str], None]) -> None:
    log("Adaptive: probing for documentation API endpoints...")
    state.detection = _probe_for_api(state.target_url)
    if state.detection and should_skip_detection(domain_of(state.target_url), state.detection.type.value):
        log(
            f"Adaptive: playbook: {state.detection.type.value} repeatedly failed for this "
            "domain while the standard crawler succeeded — skipping straight to crawler"
        )
        state.detection = None
    if state.detection:
        desc = state.detection.framework or state.detection.type.value
        log(f"Adaptive: detected {desc} at {state.detection.url}")
        state.phase = {
            DetectionType.LLMS_TXT: CrawlerPhase.FETCH_LLMS_TXT,
            DetectionType.SITEMAP: CrawlerPhase.FETCH_SITEMAP,
            DetectionType.OPENAPI: CrawlerPhase.CONVERT_OPENAPI,
            DetectionType.FRAMEWORK: CrawlerPhase.GENERATE_SCRIPT,
        }[state.detection.type]
    else:
        log("Adaptive: no API endpoint detected, using standard crawler")
        state.phase = CrawlerPhase.CRAWLER_FALLBACK


def _phase_fetch_llms_txt(state: AgentState, log: Callable[[str], None]) -> None:
    assert state.detection is not None
    log(f"Adaptive: processing llms.txt at {state.detection.url}...")
    _handle_fetch_llms_txt(state, log)


def _phase_fetch_sitemap(state: AgentState, log: Callable[[str], None]) -> None:
    assert state.detection is not None
    log(f"Adaptive: parsing sitemap at {state.detection.url}...")
    _handle_fetch_sitemap(state, log)


def _phase_convert_openapi(state: AgentState, log: Callable[[str], None]) -> None:
    assert state.detection is not None
    log(f"Adaptive: converting OpenAPI spec at {state.detection.url}...")
    _handle_convert_openapi(state, log)


# The script-pipeline phase handlers (_phase_generate_script / _phase_execute_script)
# live in the ``16_script_phases`` chunk together with their playbook reuse logic.
