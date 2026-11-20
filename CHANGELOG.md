# Changelog

All notable changes to the **Veridocs** project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-11-21

### Added
- **Demo Token Endpoint Gating**: Gated `/api/auth/demo-token` and `/api/auth/token` behind an explicit environment variable `ENABLE_DEMO_AUTH` (default: `false`). Routes are unregistered from the application router when disabled, returning 404 rather than 403.
- **Production Boot Safeguard**: Application lifespan and settings validation refuse to boot and raise a fatal configuration exception if `ENV=production` and `ENABLE_DEMO_AUTH=true`.
- **Least-Privilege Demo Tokens**: Demo tokens are strictly bound to a `demo` role with a 15-minute maximum lifetime (900 seconds) and cannot elevate to administrator or real user privileges.
- **Live LLM Evaluation Harness (`tests/evals/`)**: Added stochastic evaluation harness evaluating factual grounding against a 40-case labeled benchmark using real LLM inference.
- **Statistical Quality Gates**:
  - Multi-run stochastic evaluation ($N=5$ default, configurable via `EVAL_RUNS`).
  - Agreement rate, Cohen's kappa ($\kappa$), precision, recall, and F1 score reporting.
  - 95% Confidence Intervals calculated via Student's $t$-distribution and 1,000-sample bootstrap percentiles.
  - Automated failure gate when the lower bound of the 95% CI drops below `EVAL_THRESHOLD` (default: `0.75`).
  - Cached JSON reporting under `tests/evals/reports/`.
- **Git Commit Enforcement**: Added `.githooks/commit-msg` hook and `.commitlintrc.json` enforcing conventional commits with a short body explaining "why".
- **Documentation**: Added comprehensive `CONTRIBUTING.md` guide and updated `README.md` and `.env.example`.

### Changed
- **Test Suite Reorganization**: Separated fast canned unit test fixtures into `tests/unit/` while reserving `tests/evals/` for live LLM evaluations.
- **Pytest Configuration**: Added `@pytest.mark.live_eval` marker, configured default `addopts` to exclude live evals during standard runs, and introduced `make eval` target.

---

## [0.9.0] - 2026-11-07

### Added
- **PostgreSQL pgvector Standard**: Fully standardized on PostgreSQL with pgvector HNSW cosine indexing for persistent multi-replica vector search (FAISS completely retired).
- **Alembic Database Migrations**: Configured versioned database migrations for pgvector tables, document metadata, and chat histories.
- **Celery & Redis Asynchronous Queue**: Distributed background worker pipeline for processing OCR, layout parsing, and large SEC 10-K filings without blocking HTTP requests.
- **Multi-Page Table Stitching**: Layout-aware table extraction stitching identical markdown headers across page breaks to prevent orphaned table rows.
- **Universal LLM Multi-Provider Support**: Dynamic auto-detection and execution across OpenAI, Anthropic, DeepSeek, Groq, Google Gemini, Ollama, Mistral, OpenRouter, GitHub Models, and offline extractive fallback.
- **E2E Browser Testing**: Added Playwright end-to-end and live smoke test suites for visual document viewer and verification workflows.

### Performance
- **Disk-Offset PDF Streaming**: Streamed PDF pages directly from disk offsets to prevent memory spikes on oversized files.

---

## [0.5.0] - 2026-10-24

### Security
- **Tenant Isolation & Anti-IDOR**: Enforced user identity matching on all document sessions and asynchronous job tracking endpoints.
- **Gateway Identity Authentication**: Supported reverse proxy gateway identity headers with shared HMAC secret verification.
- **Data Lifecycle Purging**: Automated hourly background task purging expired sessions and orphaned files after 24 hours of inactivity.
- **Path Traversal Prevention**: Hardened file access logic against path traversal exploits.

### Added
- **Interactive Portfolio Showcase**: Standalone Next.js showcase deployment for Vercel demo environments.

---

## [0.1.0] - 2026-10-18

### Added
- **Initial Core Scaffolding**: FastAPI REST service with Pydantic v2 domain schemas and Server-Sent Events (SSE) query streaming.
- **Document Ingestion Engine**: Layout-aware parsing for PDF, DOCX, and TXT documents with character de-spacing and table extraction.
- **Hybrid Retrieval Architecture**: Two-stage retrieval fusing BM25 lexical search with FastEmbed ONNX dense embeddings via Reciprocal Rank Fusion (RRF $k=60$).
- **Cross-Encoder Reranking**: Neural reranking stage using `ms-marco-MiniLM-L-6-v2` for calibrated candidate relevance scoring.
- **Grounding Verification & RAG Triad**: 3-state claim grounding verification, numeric factuality validator, and automated RAG Triad observability (context relevance, groundedness, answer relevance).
- **Forensic Contradiction Matrix**: Cross-document discrepancy and numerical divergence detection engine.
- **Next.js 15 User Interface**: 3-column resizable workspace with dark-mode Tailwind CSS, Zustand state store, and PDF.js canvas visual text highlighting.
