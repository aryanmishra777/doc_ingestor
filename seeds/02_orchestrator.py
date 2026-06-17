

"""Seed discovery context models and public lightweight entry point.

Holds the page-context value object, heartbeat logger, and the simple
``discover_seed_urls`` wrapper that returns only ranked seed URLs.
"""

@dataclass(frozen=True)
class PageSeedContext:
    title: str
    headings: list[str]
    nav_labels: list[str]
    internal_links: list[str]
    script_urls: list[str]
    iframe_urls: list[str]
    interaction_urls: list[str]
    network_urls: list[str]
    final_url: str


class _HeartbeatLogger:
    def __init__(
        self,
        label: str,
        interval_seconds: float = SEED_DISCOVERY_HEARTBEAT_SECONDS,
        status_fn: Callable[[], str] | None = None,
    ):
        self._label = label
        self._interval_seconds = max(5.0, interval_seconds)
        self._status_fn = status_fn
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time = 0.0

    def __enter__(self) -> "_HeartbeatLogger":
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.2)

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            elapsed = int(time.monotonic() - self._start_time)
            detail = ""
            if self._status_fn is not None:
                try:
                    detail = self._status_fn()
                except Exception:
                    detail = ""
            body = detail or f"still looking for potential seeds via {self._label}"
            print(f"Seed discovery: {body} ({elapsed}s elapsed)...", file=sys.stderr)


def discover_seed_urls(
    start_url: str,
    max_seed_urls: int = 8,
    use_llm: bool = False,
    llm_model: str = DEFAULT_LLM_SEED_MODEL,
    llm_provider: str = DEFAULT_OLLAMA_PROVIDER,
    use_web_search: bool = False,
) -> list[str]:
    seed_urls, _ = discover_seed_urls_with_diagnostics(
        start_url=start_url,
        max_seed_urls=max_seed_urls,
        use_llm=use_llm,
        llm_model=llm_model,
        llm_provider=llm_provider,
        use_web_search=use_web_search,
    )
    return seed_urls
