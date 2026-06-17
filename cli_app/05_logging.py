

"""CLI logging and interactive seed-mode selection.

Prints concise runtime/seed-discovery diagnostics to stderr and handles the interactive
choice used by ``--seed-mode ask``.
"""

def log_runtime_config(
    env_loaded: bool,
    seed_llm_enabled: bool,
    adaptive_enabled: bool,
    seed_provider: str,
    adaptive_provider: str,
    seed_web_search: bool,
) -> None:
    key_present = bool(os.environ.get("OLLAMA_API_KEY", "").strip())
    gemini_key_present = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    print(
        "Config: "
        f"dotenv_loaded={'yes' if env_loaded else 'no'}, "
        f"ollama_key={'set' if key_present else 'missing'}, "
        f"gemini_key={'set' if gemini_key_present else 'missing'}, "
        f"seed_provider={seed_provider}, "
        f"adaptive_provider={adaptive_provider}",
        file=sys.stderr,
    )
    if seed_llm_enabled and seed_provider == "cloud" and not key_present:
        print(
            "Config note: --seed-llm uses cloud but OLLAMA_API_KEY is missing; "
            "falling back to non-LLM seed discovery.",
            file=sys.stderr,
        )
    if adaptive_enabled and adaptive_provider == "cloud" and not key_present:
        print(
            "Config note: --adaptive uses cloud for LLM steps but OLLAMA_API_KEY is missing; "
            "adaptive LLM generation will fall back when needed.",
            file=sys.stderr,
        )
    if seed_llm_enabled and seed_provider == "gemini" and not gemini_key_present:
        print(
            "Config note: --seed-llm uses Gemini but GEMINI_API_KEY is missing; "
            "falling back to non-LLM seed discovery.",
            file=sys.stderr,
        )
    if adaptive_enabled and adaptive_provider == "gemini" and not gemini_key_present:
        print(
            "Config note: --adaptive uses Gemini but GEMINI_API_KEY is missing; "
            "adaptive LLM generation will fall back when needed.",
            file=sys.stderr,
        )
    if seed_llm_enabled and seed_provider == "local" and seed_web_search:
        print(
            "Config note: local seed discovery uses DuckDuckGo web search by default (no API key needed); "
            "set DOC_INGESTOR_WEB_SEARCH_PROVIDER to use SearXNG, Brave, Tavily, or TinyFish instead.",
            file=sys.stderr,
        )
    if seed_llm_enabled and seed_provider == "gemini" and seed_web_search:
        print(
            "Config note: Gemini seed discovery will use native Google Search grounding when supported by the selected model.",
            file=sys.stderr,
        )
    if seed_llm_enabled:
        print(
            "Config note: set DOC_INGESTOR_LLM_TIMEOUT_SECONDS to cap how long seed LLM calls may run "
            "before falling back to heuristic seeds, or 'off' to wait with no cap (the live "
            "progress screen shows web-search hits and the current phase while it works).",
            file=sys.stderr,
        )


def log_seed_discovery_config(diagnostics: SeedDiscoveryDiagnostics, llm_model: str, llm_provider: str) -> None:
    if not diagnostics.llm_requested:
        return

    print(
        "Seed LLM: "
        f"requested=yes, attempted={'yes' if diagnostics.llm_attempted else 'no'}, "
        f"used={'yes' if diagnostics.llm_used else 'no'}, "
        f"provider={llm_provider}, "
        f"model={llm_model}, "
        f"reason={diagnostics.llm_reason}, "
        f"candidate_count={diagnostics.llm_candidate_count}",
        file=sys.stderr,
    )


def resolve_seed_mode(seed_mode: str, seed_urls: list[str]) -> str:
    if len(seed_urls) <= 1:
        return "single"
    if seed_mode != "ask":
        return seed_mode

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Seed URLs found; non-interactive session detected, defaulting to merged output.", file=sys.stderr)
        return "merge"

    return ask_seed_mode(seed_urls)


def ask_seed_mode(seed_urls: list[str]) -> str:
    print("Discovered potential seed URLs:", file=sys.stderr)
    for index, seed in enumerate(seed_urls, start=1):
        print(f"  {index}. {seed}", file=sys.stderr)

    print("Choose crawl output mode:", file=sys.stderr)
    print("  1) Merge all seeds into one output", file=sys.stderr)
    print("  2) Separate output per seed", file=sys.stderr)
    print("  3) Crawl only the original start URL", file=sys.stderr)

    while True:
        choice = input("Selection [1/2/3]: ").strip()
        if choice == "1":
            return "merge"
        if choice == "2":
            return "separate"
        if choice == "3":
            return "single"
        print("Invalid choice. Enter 1, 2, or 3.", file=sys.stderr)
