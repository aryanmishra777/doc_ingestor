# doc_ingestor

A self-hosted crawler that turns documentation websites and linked PDFs into clean, chunked Markdown — ready to drop into any LLM context window, RAG pipeline, or NotebookLM source.

## Why

LLMs are only as good as what they were trained on. When you're working with a library, framework, or spec that post-dates the model's training cutoff (or was never indexed at all), you need to bring the docs to the model yourself. `doc_ingestor` automates that: give it a URL, get back structured Markdown.

## Features

- Crawls any documentation site from a start URL
- Renders JavaScript-heavy pages via headless Chromium
- Extracts PDFs linked within documentation (with density-aware chunking)
- Automatic seed URL discovery — heuristic or LLM-assisted (Ollama cloud or local)
- **Adaptive mode** — probes for `llms.txt`, sitemaps, OpenAPI specs, and framework APIs before crawling; generates a targeted fetch script via Ollama when a structured endpoint is found; evaluates output quality and self-corrects up to 3 times with an XAI feedback report on failure
- Deduplication by canonical URL and content hash
- Chunked output for large crawls (default: 50 pages per file)
- No external API required for basic use

## Architecture

The refactor notes and diagrams live in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
and [`docs/DESIGN.md`](docs/DESIGN.md). They cover the layered packages, C4 views,
strategy/factory facades, and the adaptive crawler state flow.

## Requirements

- Python 3.11+
- [Playwright](https://playwright.dev/python/) (required)
- [pymupdf](https://pymupdf.readthedocs.io/) (optional — enables PDF support)
- [ollama](https://github.com/ollama/ollama-python) (optional — enables LLM-assisted seed discovery and adaptive LLM steps)
- `langchain`, `langchain-ollama`, `langchain-huggingface`, and `langchain-community` (optional — enables adaptive LangChain agents)
- OpenVINO / IPEX-LLM packages for `DOC_INGESTOR_AGENT_RUNTIME=openvino` or `ipex`

## Installation

**1. Clone and create a virtual environment**

```bash
git clone <repo-url>
cd doc_ingestor
python -m venv venv
```

Activate it:

```bash
# Linux / macOS
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (Command Prompt)
venv\Scripts\activate.bat
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

`pymupdf` and `ollama` are listed but optional. If you want a minimal install without them:

```bash
pip install playwright
```

**3. Install the Playwright browser**

This step downloads the Chromium binary used for rendering. It is required even if you only plan to crawl static sites.

```bash
python -m playwright install chromium
```

**4. (Optional) Configure environment variables**

Create a `.env` file in the project root to enable cloud LLM features:

```env
OLLAMA_API_KEY=your_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

For local Ollama, start the Ollama server and pull a model such as `gemma4:latest`. The default local host is `http://localhost:11434`; override it with `OLLAMA_HOST` if needed. The `.env` file is loaded automatically at startup. Its contents are never printed.

## Usage

**Basic crawl**

```bash
python cli.py https://docs.python.org/3/ --output python_docs.md
```

**Limit scope**

```bash
python cli.py https://docs.python.org/3/ --max-pages 100 --max-depth 3 --output python_docs.md
```

**Chunked output** (splits into multiple files when page count exceeds the limit)

```bash
python cli.py https://docs.python.org/3/ --chunk-pages 30 --output python_docs.md
```

## Seed Modes

When a documentation site has multiple entry points, `doc_ingestor` can discover and crawl them together.

| Mode | Behaviour |
|------|-----------|
| `single` | Crawl only from the given URL |
| `merge` | Crawl all discovered seeds, merge into one output |
| `separate` | Crawl all discovered seeds, one file per seed |
| `ask` | Prompt interactively (default) |

```bash
python cli.py https://docs.python.org/3/ --seed-mode merge --output python_docs.md
```

## LLM-Assisted Seed Discovery

When `--seed-llm` is set, the crawler sends the start URL and extracted page structure to an Ollama model, which suggests high-value seed URLs beyond what heuristics find. Falls back to heuristic discovery if the model call fails.

```bash
python cli.py https://docs.python.org/3/ \
  --seed-llm \
  --seed-llm-model gemma4:31b-cloud \
  --output python_docs.md
```

Use your local Ollama model instead:

```bash
python cli.py https://docs.python.org/3/ \
  --seed-llm \
  --seed-llm-provider local \
  --seed-llm-model gemma4:latest \
  --output python_docs.md
```

Use Gemini instead:

```bash
python cli.py https://docs.python.org/3/ \
  --seed-llm \
  --seed-llm-provider gemini \
  --seed-llm-model gemini-2.5-flash-lite \
  --output python_docs.md
```

Add `--seed-llm-web-search` to augment suggestions with a web search pass:

```bash
python cli.py https://docs.python.org/3/ \
  --seed-llm \
  --seed-llm-model gemma4:31b-cloud \
  --seed-llm-web-search \
  --output python_docs.md
```

Cloud mode uses Ollama's hosted web search. Local mode can also use web search if you configure an external provider.
Gemini mode uses native Google Search grounding when `--seed-llm-web-search` is enabled and the selected Gemini model supports it.

For local web search, set `DOC_INGESTOR_WEB_SEARCH_PROVIDER` to one of:

- `searxng` with `SEARXNG_BASE_URL`
- `brave` with `BRAVE_SEARCH_API_KEY`
- `tavily` with `TAVILY_API_KEY`
- `auto` to auto-detect one of the above from your environment

If your local model is slow or gets stuck during seed analysis, you can cap the seed LLM call duration:

```env
DOC_INGESTOR_LLM_TIMEOUT_SECONDS=90
```

When the timeout is hit, `doc_ingestor` logs the timeout and falls back to heuristic seed discovery instead of waiting indefinitely.

Example with local Ollama plus SearXNG:

```env
DOC_INGESTOR_WEB_SEARCH_PROVIDER=searxng
SEARXNG_BASE_URL=http://localhost:8080
```

Then run:

```bash
python cli.py https://docs.python.org/3/ \
  --seed-llm \
  --seed-llm-provider local \
  --seed-llm-model gemma4:latest \
  --seed-llm-web-search \
  --output python_docs.md
```

## Adaptive Mode

Adaptive mode runs a multi-phase agent before and after the standard crawl:

**Pre-checks (deterministic, no LLM required):**
1. Probes for `llms.txt` / `.well-known/llms.txt` — AI-native Markdown content endpoint
2. Probes for `sitemap.xml` / `sitemap_index.xml` — structured URL enumeration
3. Probes for `openapi.json` / `swagger.json` — API schema endpoints
4. Detects known doc frameworks from homepage HTML (Docusaurus, GitBook, ReadTheDocs, MkDocs)

If any endpoint is found, a LangChain script-generation agent generates a targeted Python fetch script that outputs clean JSONL directly, skipping the BFS crawl entirely. If detection fails or the model is unavailable, the standard crawler runs as normal.

**Post-checks (deterministic quality evaluation):**
- **Structural score** — fraction of records with valid URL, title, and content (threshold: >95%)
- **Density score** — average word count per page normalised to 1500 words (threshold: >15%)
- **Scope score** — record count relative to a minimum of 5 pages (threshold: ≥100%)

If quality checks fail, the agent self-corrects up to 3 times:
- Script path: rewrites the fetch script with the error trace appended as context
- Crawler path: retries with `include_sparse_pages=True`, then with no depth limit

If retries are exhausted, a LangChain feedback-analysis agent emits a report to stderr explaining the failure mode (`SELECTOR_MISMATCH`, `PAGINATION_FAILURE`, `RATE_LIMITED`, `EMPTY_CONTENT`, or `SYNTAX_ERROR`), whether a permanent fix is recommended, and what the immediate fix would be.

```bash
python cli.py https://developer.mozilla.org/en-US/docs/Web/JavaScript \
  --adaptive \
  --output mdn_js.md
```

Use a specific Ollama model for the adaptive LLM steps:

```bash
python cli.py https://docs.python.org/3/ \
  --adaptive \
  --adaptive-model gemma4:31b-cloud \
  --output python_docs.md
```

Run adaptive LLM steps locally:

```bash
python cli.py https://docs.python.org/3/ \
  --adaptive \
  --adaptive-provider local \
  --adaptive-model gemma4:latest \
  --output python_docs.md
```

Cloud mode requires `OLLAMA_API_KEY` for script generation and feedback analysis. Local mode requires a running Ollama server. The deterministic probing and quality evaluation steps run regardless.

### Adaptive Agent Runtime

By default, adaptive mode runs through LangChain agents with callable tools for detection context, retry history, output schema, quality metrics, and execution traces. If the optional LangChain stack is not installed or cannot run the selected model, `doc_ingestor` falls back to the previous direct chat path.

Use local Gemma through Ollama:

```env
DOC_INGESTOR_AGENT_RUNTIME=ollama
OLLAMA_HOST=http://localhost:11434
```

Use OpenVINO for local text generation:

```env
DOC_INGESTOR_AGENT_RUNTIME=openvino
DOC_INGESTOR_OPENVINO_MODEL=google/gemma-2-2b-it
DOC_INGESTOR_OPENVINO_DEVICE=CPU
```

Use IPEX-LLM through LangChain Community:

```env
DOC_INGESTOR_AGENT_RUNTIME=ipex
DOC_INGESTOR_IPEX_MODEL=google/gemma-2-2b-it
```

Set `DOC_INGESTOR_AGENT_MODE=direct` to bypass LangChain agents and force the legacy direct chat call.

## All Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | _(stdout)_ | Output Markdown file path |
| `--max-pages N` | unlimited | Stop after N pages |
| `--max-depth N` | unlimited | Stop after depth N |
| `--chunk-pages N` | `50` | Pages per output file |
| `--workers N` | `4` | Concurrent page fetches |
| `--include-sparse` | off | Include navigation-only pages in output |
| `--seed-mode` | `ask` | `single` / `merge` / `separate` / `ask` |
| `--seed-llm` | off | Enable LLM-assisted seed discovery |
| `--seed-llm-provider` | `cloud` | `cloud` / `local` / `gemini` provider for seed discovery |
| `--seed-llm-model` | provider default | Seed model (`gemma4:31b-cloud` for cloud, `gemma4:latest` for local, `gemini-2.5-flash-lite` for Gemini) |
| `--seed-llm-web-search` | off | Augment LLM seed suggestions with web search via Ollama cloud or a configured external provider |
| `--adaptive` | off | Enable adaptive mode (API probing + quality eval + self-correction) |
| `--adaptive-provider` | `cloud` | `cloud` / `local` / `gemini` provider for adaptive LLM steps |
| `--adaptive-model` | provider default | Adaptive model (`gemma4:31b-cloud` for cloud, `gemma4:latest` for local, `gemini-2.5-flash-lite` for Gemini) |

## Project Structure

| File | Purpose |
|------|---------|
| `cli.py` | Command-line interface and entry point |
| `pipeline.py` | Crawl loop, deduplication, output orchestration |
| `adaptive.py` | Adaptive agent — API probing, script generation, quality eval, self-correction, XAI feedback |
| `extraction.py` | HTML page extraction (Playwright + custom parser) |
| `pdf_extraction.py` | PDF extraction with density analysis |
| `seeds.py` | Seed URL discovery (heuristic + LLM) |
| `traversal.py` | Crawl frontier and URL filtering |
| `structuring.py` | Markdown rendering |
| `cleaning.py` | Text normalisation |
| `models.py` | Shared TypedDict definitions |

