# doc_ingestor

A self-hosted crawler that turns documentation websites and linked PDFs into clean, chunked Markdown — ready to drop into any LLM context window, RAG pipeline, or NotebookLM source.

## Why

LLMs are only as good as what they were trained on. When you're working with a library, framework, or spec that post-dates the model's training cutoff (or was never indexed at all), you need to bring the docs to the model yourself. `doc_ingestor` automates that: give it a URL, get back structured Markdown.

## Features

- Crawls any documentation site from a start URL
- Renders JavaScript-heavy pages via headless Chromium
- Extracts PDFs linked within documentation (with density-aware chunking)
- Automatic seed URL discovery — heuristic or LLM-assisted (Ollama)
- Deduplication by canonical URL and content hash
- Chunked output for large crawls (default: 50 pages per file)
- No external API required for basic use

## Requirements

- Python 3.11+
- [Playwright](https://playwright.dev/python/) (required)
- [pymupdf](https://pymupdf.readthedocs.io/) (optional — enables PDF support)
- [ollama](https://github.com/ollama/ollama-python) (optional — enables LLM-assisted seed discovery)

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

Create a `.env` file in the project root to enable LLM-assisted seed discovery:

```env
OLLAMA_API_KEY=your_api_key_here
```

The `.env` file is loaded automatically at startup. Its contents are never printed.

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
  --seed-llm-model gemma4:31b \
  --output python_docs.md
```

Add `--seed-llm-web-search` to augment suggestions with a web search pass:

```bash
python cli.py https://docs.python.org/3/ \
  --seed-llm \
  --seed-llm-model gemma4:31b \
  --seed-llm-web-search \
  --output python_docs.md
```

Requires `OLLAMA_API_KEY` in `.env` or the environment.

## All Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | required | Output Markdown file path |
| `--max-pages N` | unlimited | Stop after N pages |
| `--max-depth N` | unlimited | Stop after depth N |
| `--chunk-pages N` | `50` | Pages per output file |
| `--seed-mode` | `ask` | `single` / `merge` / `separate` / `ask` |
| `--seed-llm` | off | Enable LLM seed suggestions |
| `--seed-llm-model` | `gemma4:31b` | Ollama model to use |
| `--seed-llm-web-search` | off | Augment LLM suggestions with web search |

## Project Structure

| File | Purpose |
|------|---------|
| `cli.py` | Command-line interface and entry point |
| `pipeline.py` | Crawl loop, deduplication, output orchestration |
| `extraction.py` | HTML page extraction (Playwright + custom parser) |
| `pdf_extraction.py` | PDF extraction with density analysis |
| `seeds.py` | Seed URL discovery (heuristic + LLM) |
| `traversal.py` | Crawl frontier and URL filtering |
| `structuring.py` | Markdown rendering |
| `cleaning.py` | Text normalisation |
| `models.py` | Shared TypedDict definitions |
=======
# doc_ingestor
>>>>>>> 00aab5d4788a6c25a396f23b460ef7ceea218ec5
