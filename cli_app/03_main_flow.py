"""Top-level CLI flow.

Loads environment variables, resolves provider-specific model defaults, discovers seed
URLs, chooses the seed mode, and delegates final output handling.
"""

def main() -> None:
    """Parse CLI arguments, crawl records, and write or print Markdown."""
    env_loaded = load_env_file()
    args = _build_parser().parse_args()
    seed_llm_model, adaptive_model = _resolve_requested_models(args)

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
    _write_or_print_output(args, seed_urls, seed_mode, adaptive_model)


def _resolve_requested_models(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve provider-specific defaults for seed and adaptive LLM models."""
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
    return seed_llm_model, adaptive_model


def _write_or_print_output(args: argparse.Namespace, seed_urls: list[str], seed_mode: str, adaptive_model: str) -> None:
    """Write output files when requested; otherwise print merged Markdown to stdout."""
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
            return
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
        return

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
