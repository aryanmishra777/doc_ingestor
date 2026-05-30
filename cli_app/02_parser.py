"""Argument parser construction for the command-line interface.

Defines every public CLI flag in one place while leaving crawl orchestration and output
handling to the neighboring flow modules.
"""

def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the crawler CLI."""
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
    parser.add_argument("--seed-llm", action="store_true", help="Use an Ollama model to suggest extra seed URLs")
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
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent page fetches (default: 4)")
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
    return parser
