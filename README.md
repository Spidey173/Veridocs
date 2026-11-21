# 📑 Veridocs

Fast, honest, lightweight document question answering (RAG) with real page citations and citation support checks.

Runs entirely locally on an 8GB RAM laptop with **zero Docker required**.

---

## What Actually Works

- **Real Document Ingestion**: Upload multi-page PDF or TXT documents. Documents are parsed with `pypdf`, chunked into granular ~550-character passage windows with overlap, and embedded locally using Fastembed ONNX (`bge-small-en-v1.5`).
- **Realistic 6-Page Demo Document**: Ships with a realistic 6-page Master Cloud Services Agreement covering Parties, 250 Authorized Users, Fees & Overages, 99.9% SLA & Credits, AES-256 Security, and $500,000 Liability Cap.
- **Durable Local Storage**: Chunks and L2-normalized float32 vectors are stored directly in SQLite (`backend/data/veridocs.db`). No Postgres, pgvector, Redis, or Celery.
- **Fast Vector Retrieval**: Pure NumPy cosine similarity search over persistent embeddings (~3.4ms retrieval latency).
- **Streaming Answers with Real Citations**: Token-by-token streaming via Server-Sent Events (SSE). Citations pinpoint exact document names, page numbers, and passage excerpts that jump directly to that page in the PDF.
- **Real PDF Rendering**: Built-in PDF.js canvas viewer rendering actual PDF bytes from the backend with interactive page navigation.
- **Honest Citation Check**: Verifies answer claims against retrieved source chunks via n-gram overlap check. No fabricated scores or fake "RAG Triad" numbers.
- **Single OpenAI-Compatible LLM + BYOK**: Connects to any standard endpoint (OpenAI, local Ollama, Groq, vLLM) via `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. Visitors can also paste their own API key directly in the UI ("Bring Your Own Key"), stored only in the browser to bypass rate limits.
- **Public Demo Abuse Protection**: In-memory per-IP rate limiting (20 queries/hr, 10 uploads/hr), 10 MB maximum upload size, 50-page document cap, and 20 active sessions ceiling.
- **Render Cold-Start Detection**: UI monitors backend health and informs users if a free-tier backend is spinning up from sleep.

---

## Quickstart

Tested from a fresh clone. Requires **Python 3.11+** and **Node.js 18+**.

### 1. Install Dependencies
```bash
pip install -r backend/requirements.txt
npm install
```

### 2. Configure LLM (Optional)
Create a `.env` file in the project root:
```bash
# Hosted OpenAI
OPENAI_API_KEY=sk-...

# Or Local Ollama (100% private, zero cost)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.2

# Or any OpenAI-compatible provider (e.g. Groq)
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...
LLM_MODEL=llama-3.3-70b-versatile
```
*(If omitted, vector search, PDF viewing, and document indexing still work completely. The UI displays an honest banner explaining that an LLM key is needed for generated answers, or visitors can paste their own key directly into the UI).*

### 3. Run Dev Server
```bash
npm run dev
```
- **Web App**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

---

## Performance & Memory Benchmarks

Measured on macOS (Apple Silicon, 8GB RAM baseline):

| Metric | Measured Value | Notes |
| :--- | :--- | :--- |
| **RAM Usage (Idle)** | **~302 MB** | Baseline Python runtime + loaded Fastembed ONNX session |
| **RAM Usage (Peak Querying)** | **~311 MB** | Fully stable under 500 MB (runs easily on 8GB laptops) |
| **Fastembed Model Download** | **~133 MB** | One-time download on first cold run (5–15s), cached locally |
| **Model Init from Disk Cache** | **~360 ms** | Once cached, loads locally in under half a second |
| **6-Page PDF Ingestion & Embed** | **~207 ms** | ~34.6 ms per passage chunk |
| **Vector Retrieval Latency** | **~3.4 ms** | SQLite scan + NumPy dot product cosine similarity |
| **Citation Check Latency** | **~0.3 ms** | N-gram claim overlap analysis |

---

## Architecture

```
Veridocs/
├── app/                  # Next.js App Router (layout, page, styles)
├── components/           # React UI components (PDF viewer, Chat, Upload, Layout)
├── lib/                  # Zustand store and API client
├── public/               # Static assets & PDF.js worker
├── tests/                # Frontend Vitest test suite (10 tests)
├── backend/
│   ├── main.py           # FastAPI entrypoint, lifespan & CORS
│   ├── database.py       # SQLite chunk & vector persistence + TTL cleanup
│   ├── vector_store.py   # Vector retrieval with NumPy dot product
│   ├── llm_service.py    # OpenAI-compatible streaming client
│   ├── pdf_processor.py  # pypdf text extraction, granular chunker & sample generator
│   ├── verification.py   # N-gram citation claim check
│   ├── rate_limiter.py   # Per-IP sliding window abuse protection
│   ├── config.py         # App configuration & Fastembed model registry
│   └── tests/            # 16 backend behavior pytest tests
├── package.json          # Single package.json for frontend, test & dev orchestration
└── scripts/
    ├── dev.js            # Starts FastAPI and Next.js concurrently
    ├── test_live_e2e.py  # Real HTTP port-binding integration smoke test
    ├── test_real_llm.py  # Live OpenAI-compatible LLM streaming verification
    └── measure_performance.py # RSS memory and latency benchmark
```

---

## Verification & Tests

### Run Full Test Suite (Frontend + Backend)
```bash
npm test
```
*Runs frontend Vitest suite (10 tests in ~350ms) and backend Pytest suite (16 tests in ~1.5s).*

### Production Build
```bash
npm run build
```
*Result: Compiled successfully with zero TypeScript or webpack errors in ~1.5s.*

---

## Deployment & Environment Variables

### 1. Backend on Render (Web Service)
- **Runtime**: Docker (points to `backend/Dockerfile`).
- **Build**: Fastembed ONNX weights (`bge-small-en-v1.5`) are pre-downloaded during Docker build so the image starts up quickly without downloading weights at runtime.
- **Environment Variables**:
  | Variable | Value | Description |
  | :--- | :--- | :--- |
  | `FRONTEND_ORIGIN` | `https://your-app.vercel.app` | Allowed CORS origin (also auto-allows `*.vercel.app` previews) |
  | `OPENAI_API_KEY` | `sk-...` | (Optional) Server-side fallback LLM key |
  | `RATE_LIMIT_QUERY_PER_HOUR` | `20` | Max queries/hour per IP (BYOK users bypass this limit) |
  | `MAX_FILE_SIZE_MB` | `10` | Max upload size in megabytes |

### 2. Frontend on Vercel
- **Framework**: Next.js (Root Directory: `.`).
- **Environment Variables**:
  | Variable | Value | Description |
  | :--- | :--- | :--- |
  | `NEXT_PUBLIC_API_URL` | `https://your-backend.onrender.com` | Render backend URL |

---

## Known Limitations

1. **Ephemeral Storage on Render Free Tier**: Render's free tier uses an ephemeral filesystem. On container restarts or after spinning down from inactivity (~15 minutes idle), custom uploaded documents reset. The bundled 6-page `sample_agreement.pdf` is automatically re-indexed on boot for showcase testing. An automatic 24-hour TTL and 20-session limit in `database.py` prevents disk growth while the container is running.
2. **Cold Starts on Free Hosting**: Render free instances spin down when idle. Cold starts take **30–60 seconds** to wake up the container. The frontend detects this and displays a "Backend is waking up" indicator.
3. **Single-User Workspace**: Veridocs is designed for single-user document inspection and local execution; it does not include multi-tenant organization management or document RBAC.
4. **Citation Check Methodology**: The citation check is an **n-gram text overlap heuristic** verifying whether answer claims literally appear in the retrieved context chunks. It is not an expensive multi-judge LLM evaluation model.

---

## License

MIT
