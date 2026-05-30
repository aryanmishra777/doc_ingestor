# Architecture

This refactor keeps the public CLI and import surface stable while organizing the crawler
behind layered package facades.

## C1 System Context

```mermaid
C4Context
    title doc_ingestor system context
    Person(user, "User", "Runs the CLI and reads NotebookLM-ready Markdown")
    System(doc, "doc_ingestor", "Discovers, crawls, extracts, cleans, and renders documentation")
    System_Ext(site, "Documentation sites", "HTML, Markdown, PDF, sitemap, robots.txt, llms.txt, OpenAPI")
    System_Ext(llm, "LLM providers", "Ollama cloud/local and Gemini")
    System_Ext(search, "Web search providers", "SearXNG, Brave, Tavily, provider-native search")
    System_Ext(browser, "Playwright/Chromium", "Browser rendering and link discovery")
    Rel(user, doc, "Runs")
    Rel(doc, site, "Fetches")
    Rel(doc, llm, "Asks for seed/adaptive guidance")
    Rel(doc, search, "Finds candidate seed URLs")
    Rel(doc, browser, "Renders dynamic pages")
```

## C2 Containers

```mermaid
C4Container
    title doc_ingestor containers
    Container(cli, "cli / cli_app", "Python", "Argument parsing and output routing")
    Container(pipeline, "pipeline", "Python", "Concurrent crawl facade")
    Container(traversal, "traversal", "Python", "Frontier and URL rules")
    Container(extraction, "extraction", "Python", "HTML/browser/PDF/Markdown extraction strategies")
    Container(cleaning, "cleaning", "Python", "Record cleanup")
    Container(structuring, "structuring", "Python", "Markdown rendering")
    Container(seeds, "seeds", "Python", "Seed discovery facade")
    Container(adaptive, "adaptive", "Python", "Adaptive probe/fetch/evaluate state machine")
    Container(llm, "llm", "Python", "Provider strategies and factory")
    Container(net, "net", "Python", "Shared HTTP client")
    Container(domain, "domain", "Python", "TypedDict records and helpers")
    Rel(cli, seeds, "Discovers starts")
    Rel(cli, adaptive, "Optional adaptive crawl")
    Rel(cli, pipeline, "Standard crawl")
    Rel(pipeline, traversal, "Dequeues URLs")
    Rel(pipeline, extraction, "Extracts pages")
    Rel(pipeline, cleaning, "Cleans records")
    Rel(cli, structuring, "Renders Markdown")
    Rel(seeds, llm, "Uses")
    Rel(adaptive, llm, "Uses")
    Rel(seeds, net, "Fetches")
    Rel(adaptive, net, "Fetches")
    Rel(extraction, domain, "Produces records")
```

## C3 Components

```mermaid
flowchart LR
    subgraph adaptive
        S[AgentState] --> P[phase handlers]
        P --> L[llms.txt]
        P --> M[sitemap]
        P --> O[OpenAPI/framework probes]
        P --> E[evaluation/self-correction]
    end
    subgraph seeds
        H[heuristics] --> R[robots/sitemap]
        R --> C[page context]
        C --> LLM[LLM seed suggestions]
        LLM --> W[web search providers]
        W --> K[live ranking]
    end
```

## C4 Code

```mermaid
classDiagram
    class DocPageRecord
    class ContentBlock
    class CodeBlock
    class LLMClient {
      <<protocol>>
      chat(messages)
    }
    class OllamaClient
    class GeminiClient
    class BrowserPool
    class LinkTraversalFrontier
    class PipelineResult
    LLMClient <|.. OllamaClient
    LLMClient <|.. GeminiClient
    BrowserPool --> DocPageRecord
    LinkTraversalFrontier --> DocPageRecord
    PipelineResult --> DocPageRecord
```
