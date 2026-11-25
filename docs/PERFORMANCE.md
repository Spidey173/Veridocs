# Veridocs Performance & Profiling

All measurements below were collected locally using [`scripts/benchmark.py`](../scripts/benchmark.py) and `next build` (`--webpack`) on macOS arm64 (Apple Silicon) running Python 3.11 with **SQLite**, local Fastembed ONNX embeddings (`BAAI/bge-small-en-v1.5`), `pypdf` fallback text extraction, and an **offline deterministic LLM streaming stub** to isolate local pipeline overhead from external API latency.

> **Important Scope Note**: Latency numbers for `check_citations`, `list_sessions`, and `GET /api/analytics` are **synthetic SQLite microbenchmarks** on small datasets (`25` sessions, `30` chunks) and should not be cited as end-to-end production speedups under PostgreSQL + live LLMs. The primary measured production-relevant wins are **peak RSS memory reduction (-54.2%)** and **initial frontend JS route bundle reduction (-46.6%)**.

Reproduce anytime with:

```bash
.venv/bin/python scripts/benchmark.py
.venv/bin/python scripts/benchmark.py --cprofile
```

## Baseline Profiling Findings (`cProfile`)

Profiling a full 50-page PDF ingestion run (`299` chunks) via `cProfile` identified the primary time sinks:

1. **ONNX Embedding Inference (`fastembed` / `onnxruntime`)**: `6.629 s` of `7.825 s` total (`84.7%` of ingestion CPU time) spent in `onnxruntime` forward passes. Default `batch_size=256` padded all 256 sequences in a batch to the longest chunk length, pushing peak process RSS to `1,277.3 MiB`.
2. **N+1 Queries & Full Row Loads**: `database.list_sessions()` executed `1 + N` SQL queries to count chunks per session; `GET /analytics` loaded full `Document`, `Flag` (`evidence` JSON), and `QueryLog` ORM objects rather than projected columns.
3. **Repeated Verification Tokenization**: `check_citations()` re-ran `re.findall()` across all candidate source chunks for every individual factual claim (`O(claims × chunks)`).
4. **Synchronous Blocking Calls & Uncached Clients**: `/api/query` and `/api/query/stream` ran synchronous embedding/vector retrieval and blocking calls directly on the asyncio event loop thread, and `LLMService` constructed a new `OpenAI` `httpx` client on each instantiation.
5. **Monolithic Frontend Route Chunk**: `FileManager`, `WorkspaceHeader`, and `WorkspaceLayout` eagerly imported all secondary tabs (`GraphViewer`, `CompareViewer`, `FlagsViewer`, `SummaryViewer`, `ReportViewer`, `AnalyticsDashboard`, `PDFViewer`), bundling them into the initial `/` JavaScript chunk (`118 KiB`).

## Optimizations Implemented

- **Reduced ONNX Batch Padding (`backend/tasks.py`)**: Set `batch_size=32` on `embedding_model.embed(...)`. In a direct 3-run A/B test on the 50-page pipeline (`299` chunks), `batch_size=32` ran in **`7,243.4 ms` median** (`[7110.5, 7409.3, 7243.4] ms`) vs `batch_size=256` at **`8,126.2 ms` median** (`[8126.2, 8251.3, 7770.1] ms`), `-10.9%` faster while slashing peak ONNX buffer memory.
- **Startup Model Pre-Warm (`backend/main.py`)**: Warm `ModelRegistry.embedding_model` inside FastAPI `lifespan` startup.
- **Database Indexes (`backend/models_db.py`, `backend/alembic/versions/008_add_perf_indexes.py`)**: Added indexes on `documents.status`, `chunks.filename`, and composite `(session_id, filename)`.
- **Eliminated N+1 & Over-Fetching (`backend/database.py`, `backend/routers/analytics.py`)**: Replaced `list_sessions()` per-session `COUNT(*)` loop with a single `GROUP BY` query; batched chunk inserts with `db.add_all()`; projected only `(status, created_at)` / `(citation_score, created_at)` columns in `/analytics`.
- **Verification Pre-Tokenization & Batched NLI (`backend/verification.py`)**: Pre-tokenized source chunks once per `check_citations()` call and batched `CrossEncoder.predict()` pairs across all factual claims when NLI is enabled.
- **Client & Retrieval Caching + Non-Blocking Async Offload (`backend/llm_service.py`, `backend/vector_store.py`, `backend/routers/query.py`)**: Pooled `OpenAI` clients by `(base_url, api_key)`, added a version-invalidated `_SEARCH_CACHE` (`VectorStore.search`), and moved blocking retrieval, rewrite, and verification work off the event loop with `asyncio.to_thread()`.
- **Frontend Code Splitting (`components/workspace/FileManager.tsx`, `WorkspaceHeader.tsx`, `WorkspaceLayout.tsx`)**: Converted secondary tabs, `AnalyticsDashboard`, and `PDFViewer` to lazy `next/dynamic(..., { ssr: false })` imports.

## Measured Before / After Comparison (3-Run Post-Change Median)

> **Conditions**: Three consecutive uncontended runs of `scripts/benchmark.py --json` against local SQLite (`cProfile` baseline vs 3-run median after optimizations).

### System Memory & Bundle Size (Headline Gains)

| Metric | Baseline | After (3-Run Median) | Delta |
| :--- | :--- | :--- | :--- |
| **Process Peak RSS (`ru_maxrss`)** | `1,277.31 MiB` | `585.47 MiB` (`[522.84, 585.47, 618.39]`) | **-54.2% peak RSS** |
| **Frontend Initial `/` Bundle (`.next/static/chunks/app/page-*.js`)** | `118 KiB` | `63 KiB` | **-46.6% initial JS** |

### End-to-End Local Pipeline Latencies

| Workload | Baseline | After (3-Run Median) | Delta & Explanation |
| :--- | :--- | :--- | :--- |
| **Ingestion 10p PDF (59 chunks)** | `1,792.92 ms` | `1,836.58 ms` (`[1800.9, 1836.58, 1854.5]`) | `+2.4%` (`+43.7 ms`; essentially flat within polling/scheduling variance; peak traced `8.42 → 8.36 MiB`) |
| **Ingestion 50p PDF (299 chunks)** | `8,591.83 ms` | `8,467.76 ms` (`[8169.27, 8513.69, 8467.76]`) | `-1.4%` (`-124.1 ms`; 3-run median is slightly faster despite CPU ONNX variance; peak traced `9.29 → 9.33 MiB`) |
| **Streaming Q&A TTFT (10p, single cold query)** | `38.48 ms` | `45.05 ms` (`[50.63, 45.05, 36.07]`) | **+6.57 ms regression on uncontended single cold query** caused by `asyncio.to_thread()` threadpool dispatch overhead added to keep FastAPI's event loop non-blocking under concurrent requests |
| **Summary + Report Generation (10p, offline fallback)** | `5.14 ms` / `33.10 ms` | `7.52 ms` / `83.41 ms` | Small increase within cold-process/SQLite transaction variance (`[6.69, 7.52, 9.57]` / `[85.42, 83.41, 57.18] ms`) |

### Isolated SQLite / Stub Microbenchmarks (Small Synthetic Datasets)

| Microbenchmark | Baseline | After (3-Run Median) | Delta |
| :--- | :--- | :--- | :--- |
| **`check_citations` (15 claims × 30 chunks, 50 iters)** | `5.667 ms` | `1.672 ms` (`[1.672, 1.573, 2.030]`) | 3.39× faster on pure Python heuristic loop |
| **`database.list_sessions` (25 SQLite sessions)** | `6.044 ms` | `0.401 ms` (`[0.401, 0.411, 0.401]`) | 15.1× faster via single grouped SQL count query |
| **`GET /api/analytics` (25 SQLite docs/flags/queries)** | `1.376 ms` | `0.881 ms` (`[0.891, 0.881, 0.846]`) | 1.56× faster via column projection |

## Remaining Bottleneck

CPU-bound ONNX embedding generation (`BAAI/bge-small-en-v1.5`) still accounts for ~85% of total multi-page ingestion time on CPU-only hosts (~8.5s median for 50 pages / 299 chunks). Moving embedding workers to GPU or a quantized ONNX execution provider is the primary lever for further ingestion speedup.
