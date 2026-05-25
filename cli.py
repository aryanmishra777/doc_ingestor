from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

if __package__:
    from .adaptive import (
        DEFAULT_ADAPTIVE_MODEL,
        DEFAULT_CLOUD_ADAPTIVE_MODEL,
        DEFAULT_GEMINI_ADAPTIVE_MODEL,
        DEFAULT_LOCAL_ADAPTIVE_MODEL,
        collect_records_adaptive,
    )
    from .models import DocPageRecord
    from .pipeline import DEFAULT_CHUNK_PAGES, collect_records, write_markdown_outputs
    from .seeds import (
        DEFAULT_CLOUD_LLM_SEED_MODEL,
        DEFAULT_GEMINI_LLM_SEED_MODEL,
        DEFAULT_LLM_SEED_MODEL,
        DEFAULT_LOCAL_LLM_SEED_MODEL,
        SeedDiscoveryDiagnostics,
        discover_seed_urls_with_diagnostics,
    )
    from .structuring import structure_records_to_markdown
else:
    sys.path.append(str(Path(__file__).resolve().parent))
    from adaptive import (
        DEFAULT_ADAPTIVE_MODEL,
        DEFAULT_CLOUD_ADAPTIVE_MODEL,
        DEFAULT_GEMINI_ADAPTIVE_MODEL,
        DEFAULT_LOCAL_ADAPTIVE_MODEL,
        collect_records_adaptive,
    )
    from models import DocPageRecord
    from pipeline import DEFAULT_CHUNK_PAGES, collect_records, write_markdown_outputs
    from seeds import (
        DEFAULT_CLOUD_LLM_SEED_MODEL,
        DEFAULT_GEMINI_LLM_SEED_MODEL,
        DEFAULT_LLM_SEED_MODEL,
        DEFAULT_LOCAL_LLM_SEED_MODEL,
        SeedDiscoveryDiagnostics,
        discover_seed_urls_with_diagnostics,
    )
    from structuring import structure_records_to_markdown


DEFAULT_START_URL = "https://example.com/docs"


def main() -> None:
    env_loaded = load_env_file()

    parser = argparse.ArgumentParser(description="Ingest documentation into NotebookLM-ready Markdown.")
    parser.add_argument("start_url", nargs="?", default=None, help="Documentation URL to crawl")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages to crawl (no limit if not specified)")
    parser.add_argument("--max-depth", type=int, default=None, help="Maximum crawl depth (no limit if not specified)")
    parser.add_argument(
        "--seed-mode",
        choices=("single", "merge", "separate", "ask"),
        default="ask",
        help=(
            "How to handle known seed URLs for sparse doc homepages: "
            "single (only start URL), merge (crawl known seeds into one output), "
            "separate (one output per seed), ask (prompt when known seeds are found)."
        ),
    )
    parser.add_argument(
        "--seed-llm",
        action="store_true",
        help="Use an Ollama model to suggest extra seed URLs",
    )
    parser.add_argument(
        "--seed-llm-provider",
        choices=("cloud", "local", "gemini"),
        default="cloud",
        help="LLM provider for seed suggestions; Ollama cloud, Ollama local, or Gemini",
    )
    parser.add_argument(
        "--seed-llm-model",
        default=None,
        help=(
            "Model for seed suggestions; defaults to "
            f"{DEFAULT_CLOUD_LLM_SEED_MODEL} for cloud, {DEFAULT_LOCAL_LLM_SEED_MODEL} for local, "
            f"or {DEFAULT_GEMINI_LLM_SEED_MODEL} for Gemini"
        ),
    )
    parser.add_argument(
        "--seed-llm-web-search",
        action="store_true",
        help="Enable web search while generating LLM seed URLs; uses Ollama cloud search, Gemini grounding, or a configured external provider",
    )
    parser.add_argument(
        "--chunk-pages",
        type=int,
        default=DEFAULT_CHUNK_PAGES,
        help=f"Maximum pages per Markdown output file; default is {DEFAULT_CHUNK_PAGES}",
    )
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output Markdown file")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent page fetches (default: 4)",
    )
    parser.add_argument(
        "--include-sparse",
        action="store_true",
        help="Include sparse/navigation-only pages as content in the output instead of using them only for link discovery",
    )
    parser.add_argument(
        "--adaptive",
        action="store_true",
        help=(
            "Enable adaptive mode: probe for llms.txt / sitemap / OpenAPI / framework APIs before crawling, "
            "generate a targeted fetch script via Ollama when an API is found, "
            "then evaluate output quality and self-correct up to 3 times. "
            "Falls back to the standard crawler when no API is detected or script generation fails. "
            "Cloud LLM steps require OLLAMA_API_KEY, local LLM steps require a running Ollama server, "
            "and Gemini requires GEMINI_API_KEY."
        ),
    )
    parser.add_argument(
        "--adaptive-model",
        default=None,
        help=(
            "Model used for adaptive script generation and feedback analysis; defaults to "
            f"{DEFAULT_CLOUD_ADAPTIVE_MODEL} for cloud, {DEFAULT_LOCAL_ADAPTIVE_MODEL} for local, "
            f"or {DEFAULT_GEMINI_ADAPTIVE_MODEL} for Gemini"
        ),
    )
    parser.add_argument(
        "--adaptive-provider",
        choices=("cloud", "local", "gemini"),
        default="cloud",
        help="LLM provider for adaptive steps; Ollama cloud, Ollama local, or Gemini",
    )
    args = parser.parse_args()

    seed_llm_model = resolve_provider_model(
        args.seed_llm_model,
        provider=args.seed_llm_provider,
        cloud_default=DEFAULT_CLOUD_LLM_SEED_MODEL,
        local_default=DEFAULT_LOCAL_LLM_SEED_MODEL,
        gemini_default=DEFAULT_GEMINI_LLM_SEED_MODEL,
    )
    adaptive_model = resolve_provider_model(
        args.adaptive_model,
        provider=args.adaptive_provider,
        cloud_default=DEFAULT_CLOUD_ADAPTIVE_MODEL,
        local_default=DEFAULT_LOCAL_ADAPTIVE_MODEL,
        gemini_default=DEFAULT_GEMINI_ADAPTIVE_MODEL,
    )

    log_runtime_config(
        env_loaded,
        seed_llm_enabled=args.seed_llm,
        adaptive_enabled=args.adaptive,
        seed_provider=args.seed_llm_provider,
        adaptive_provider=args.adaptive_provider,
        seed_web_search=args.seed_llm_web_search,
    )

    start_url = resolve_start_url(args.start_url)
    seed_urls, seed_diag = resolve_seed_urls_and_diagnostics(
        start_url=start_url,
        seed_mode=args.seed_mode,
        use_llm=args.seed_llm,
        llm_model=seed_llm_model,
        llm_provider=args.seed_llm_provider,
        use_web_search=args.seed_llm_web_search,
    )
    log_seed_discovery_config(seed_diag, llm_model=seed_llm_model, llm_provider=args.seed_llm_provider)
    seed_mode = resolve_seed_mode(args.seed_mode, seed_urls)
    if seed_mode == "single":
        seed_urls = [start_url]

    if args.output:
        if seed_mode == "separate" and len(seed_urls) > 1:
            write_outputs_per_seed(
                seed_urls,
                output=args.output,
                max_pages=args.max_pages,
                max_depth=args.max_depth,
                chunk_pages=args.chunk_pages,
                max_workers=args.workers,
                include_sparse_pages=args.include_sparse,
                adaptive=args.adaptive,
                adaptive_model=adaptive_model,
                adaptive_provider=args.adaptive_provider,
            )
        else:
            records = collect_records_for_seeds(
                seed_urls,
                max_pages=args.max_pages,
                max_depth=args.max_depth,
                max_workers=args.workers,
                include_sparse_pages=args.include_sparse,
                adaptive=args.adaptive,
                adaptive_model=adaptive_model,
                adaptive_provider=args.adaptive_provider,
            )
            write_markdown_outputs(records, args.output, chunk_pages=args.chunk_pages)
    else:
        if seed_mode == "separate" and len(seed_urls) > 1:
            print("Note: --seed-mode=separate requires --output; falling back to merged output.", file=sys.stderr)
        records = collect_records_for_seeds(
            seed_urls,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            max_workers=args.workers,
            include_sparse_pages=args.include_sparse,
            adaptive=args.adaptive,
            adaptive_model=adaptive_model,
            adaptive_provider=args.adaptive_provider,
        )
        print(structure_records_to_markdown(records))


def resolve_start_url(start_url: str | None) -> str:
    if start_url:
        return start_url

    entered_url = input(f"Documentation URL [{DEFAULT_START_URL}]: ").strip()
    return entered_url or DEFAULT_START_URL


def resolve_seed_urls_and_diagnostics(
    start_url: str,
    seed_mode: str,
    use_llm: bool,
    llm_model: str,
    llm_provider: str,
    use_web_search: bool,
) -> tuple[list[str], SeedDiscoveryDiagnostics]:
    if seed_mode == "single":
        diagnostics = SeedDiscoveryDiagnostics(
            llm_requested=use_llm,
            llm_attempted=False,
            llm_used=False,
            llm_reason="seed-mode-single",
            llm_candidate_count=0,
        )
        return [start_url], diagnostics

    return discover_seed_urls_with_diagnostics(
        start_url,
        use_llm=use_llm,
        llm_model=llm_model,
        llm_provider=llm_provider,
        use_web_search=use_web_search,
    )


def load_env_file(env_path: Path | None = None) -> bool:
    target_path = env_path or Path(__file__).resolve().parent / ".env"
    if not target_path.exists():
        return False

    for raw_line in target_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        cleaned_value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, cleaned_value)

    return True


def resolve_provider_model(
    selected_model: str | None,
    provider: str,
    cloud_default: str,
    local_default: str,
    gemini_default: str,
) -> str:
    if selected_model:
        return selected_model
    if provider == "local":
        return local_default
    if provider == "gemini":
        return gemini_default
    return cloud_default


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
            "Config note: local seed discovery will use an external web search provider when configured "
            "(DOC_INGESTOR_WEB_SEARCH_PROVIDER with SearXNG, Brave, or Tavily settings).",
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
            "before falling back to heuristic seeds.",
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


def collect_records_for_seeds(
    seed_urls: list[str],
    max_pages: int | None,
    max_depth: int | None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
    adaptive: bool = False,
    adaptive_model: str = DEFAULT_ADAPTIVE_MODEL,
    adaptive_provider: str = "cloud",
) -> list[DocPageRecord]:
    all_records: list[DocPageRecord] = []
    seen_urls: set[str] = set()
    seen_canonical_urls: set[str] = set()

    for seed_url in seed_urls:
        records = _collect_seed_records(
            seed_url,
            max_pages=max_pages,
            max_depth=max_depth,
            max_workers=max_workers,
            include_sparse_pages=include_sparse_pages,
            adaptive=adaptive,
            adaptive_model=adaptive_model,
            adaptive_provider=adaptive_provider,
        )
        if records is None:
            continue
        for record in records:
            _append_if_unique_record(
                record,
                all_records,
                seen_urls=seen_urls,
                seen_canonical_urls=seen_canonical_urls,
            )

    return all_records


def _append_if_unique_record(
    record: DocPageRecord,
    all_records: list[DocPageRecord],
    seen_urls: set[str],
    seen_canonical_urls: set[str],
) -> None:
    canonical_url = (record.get("canonical_url") or "").strip()
    record_url = (record.get("url") or "").strip()

    if canonical_url and canonical_url in seen_canonical_urls:
        return
    if record_url and record_url in seen_urls:
        return

    if canonical_url:
        seen_canonical_urls.add(canonical_url)
    if record_url:
        seen_urls.add(record_url)
    all_records.append(record)


def write_outputs_per_seed(
    seed_urls: list[str],
    output: Path,
    max_pages: int | None,
    max_depth: int | None,
    chunk_pages: int,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
    adaptive: bool = False,
    adaptive_model: str = DEFAULT_ADAPTIVE_MODEL,
    adaptive_provider: str = "cloud",
) -> None:
    total = len(seed_urls)
    for index, seed_url in enumerate(seed_urls, start=1):
        records = _collect_seed_records(
            seed_url,
            max_pages=max_pages,
            max_depth=max_depth,
            max_workers=max_workers,
            include_sparse_pages=include_sparse_pages,
            adaptive=adaptive,
            adaptive_model=adaptive_model,
            adaptive_provider=adaptive_provider,
        )
        if records is None:
            continue
        seed_output = _build_seed_output_path(output, seed_url, index=index, total=total)
        write_markdown_outputs(records, seed_output, chunk_pages=chunk_pages)


def _collect_seed_records(
    seed_url: str,
    max_pages: int | None,
    max_depth: int | None,
    max_workers: int = 4,
    include_sparse_pages: bool = False,
    adaptive: bool = False,
    adaptive_model: str = DEFAULT_ADAPTIVE_MODEL,
    adaptive_provider: str = "cloud",
) -> list[DocPageRecord] | None:
    try:
        if adaptive:
            records, _ = collect_records_adaptive(
                seed_url,
                max_pages=max_pages,
                max_depth=max_depth,
                max_workers=max_workers,
                include_sparse_pages=include_sparse_pages,
                llm_model=adaptive_model,
                llm_provider=adaptive_provider,
            )
        else:
            records, _ = collect_records(
                seed_url,
                max_pages=max_pages,
                max_depth=max_depth,
                max_workers=max_workers,
                include_sparse_pages=include_sparse_pages,
            )
        return records
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"Seed crawl failed for {seed_url}: {exc}", file=sys.stderr)
        return None


def _build_seed_output_path(output: Path, seed_url: str, index: int, total: int) -> Path:
    parsed = urlparse(seed_url)
    slug = (parsed.path.strip("/") or "root").replace("/", "_").replace(".", "_")
    suffix = output.suffix or ".md"

    if output.suffix:
        filename = f"{output.stem}_seed_{index:02d}_of_{total:02d}_{slug}{suffix}"
        return output.parent / filename

    output.mkdir(parents=True, exist_ok=True)
    filename = f"seed_{index:02d}_of_{total:02d}_{slug}{suffix}"
    return output / filename


if __name__ == "__main__":
    main()
