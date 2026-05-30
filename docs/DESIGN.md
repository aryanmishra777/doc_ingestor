# Design

The codebase uses small facades to preserve the old imports while moving shared concerns
into focused packages.

## Strategy Families

```mermaid
classDiagram
    class Extractor {
      <<protocol>>
      extract(url)
    }
    class HtmlExtractor
    class BrowserExtractor
    class PdfExtractor
    class MarkdownExtractor
    class LLMClient {
      <<protocol>>
      chat(messages)
    }
    class OllamaClient
    class GeminiClient
    Extractor <|.. HtmlExtractor
    Extractor <|.. BrowserExtractor
    Extractor <|.. PdfExtractor
    Extractor <|.. MarkdownExtractor
    LLMClient <|.. OllamaClient
    LLMClient <|.. GeminiClient
```

## Standard Crawl

```mermaid
sequenceDiagram
    participant CLI
    participant Pipeline
    participant Frontier
    participant Fetch
    participant Extractor
    participant Cleaning
    participant Rendering
    CLI->>Pipeline: collect_records(start_url)
    Pipeline->>Frontier: get_next_url()
    Pipeline->>Fetch: page_fetch(url)
    Fetch->>Extractor: extract by URL/content type
    Extractor-->>Pipeline: DocPageRecord
    Pipeline->>Cleaning: clean_record(record)
    Pipeline->>Frontier: register discovered links
    CLI->>Rendering: structure_records_to_markdown(records)
```

## Adaptive State

```mermaid
stateDiagram-v2
    [*] --> Init
    Init --> Probe
    Probe --> FetchLlmsTxt
    Probe --> FetchSitemap
    Probe --> GenerateScript
    FetchLlmsTxt --> Evaluate
    FetchSitemap --> Evaluate
    GenerateScript --> ExecuteScript
    ExecuteScript --> Evaluate
    Evaluate --> SelfCorrect: quality too low
    SelfCorrect --> GenerateScript
    Evaluate --> Fallback: no usable result
    Evaluate --> Done: accepted
    Fallback --> Done
```

## Seed Discovery

```mermaid
sequenceDiagram
    participant CLI
    participant Seeds
    participant Site
    participant LLM
    participant Search
    CLI->>Seeds: discover_seed_urls_with_diagnostics()
    Seeds->>Site: probe homepage, robots, sitemap
    Seeds->>LLM: optional suggestions
    Seeds->>Search: optional web search
    Seeds->>Site: live-probe candidates
    Seeds-->>CLI: ranked seed URLs + diagnostics
```
