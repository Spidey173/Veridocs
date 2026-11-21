# 📑 Veridocs

Fast, honest, lightweight document question answering (RAG) with real page citations and citation support checks.

Runs entirely locally on an 8GB RAM laptop with **zero Docker required**.

---

## What Actually Works

- **Real Document Ingestion**: Upload PDF or TXT documents. Documents are parsed with `pypdf`, chunked with sliding window overlap, and embedded locally using Fastembed ONNX (`bge-small-en-v1.5`).
- **Durable Local Storage**: Chunks and L2-normalized float32 vectors are stored directly in SQLite (`veridocs.db`). No Postgres, pgvector, Redis, or Celery.
- **Fast Vector Retrieval**: Pure NumPy cosine similarity search over persistent embeddings (<1ms query latency).
- **Streaming Answers with Real Citations**: Token-by-token streaming via Server-Sent Events (SSE). Citations include exact document names and page numbers that jump directly to that page in the PDF.
- **Real PDF Rendering**: Built-in PDF.js canvas viewer rendering actual PDF bytes from the backend with page navigation.
- **Honest Citation Check**: Verifies answer claims against retrieved source chunks via n-gram overlap check. No fabricated scores or fake "RAG Triad" numbers.
- **Single OpenAI-Compatible LLM**: Connects to any standard endpoint (OpenAI, local Ollama, vLLM) via `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. If no LLM is configured, an honest banner is displayed instead of silent fake output.
- **Render Cold-Start Detection**: UI monitors backend health and informs users if the free-tier backend is waking up.

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

# Or Local Ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.2
```
*(If omitted, vector search, PDF viewing, and document indexing still work completely. The UI will show a banner explaining that an LLM key is needed for generated answers).*

### 3. Run Dev Server
```bash
npm run dev
```
- **Web App**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

---

## Architecture

```
Veridocs/
├── app/                  # Next.js App Router (layout, page, styles)
├── components/           # React UI components (PDF viewer, Chat, Upload, Layout)
├── lib/                  # Zustand store and API client
├── public/               # Static assets & PDF.js worker
├── backend/
│   ├── main.py           # FastAPI entrypoint & lifecycle
│   ├── database.py       # SQLite chunk & vector persistence
│   ├── vector_store.py   # Vector retrieval with NumPy dot product
│   ├── llm_service.py    # OpenAI-compatible streaming client
│   ├── pdf_processor.py  # pypdf text extraction & chunker
│   ├── verification.py   # N-gram citation claim check
│   ├── config.py         # App configuration & Fastembed model registry
│   └── tests/            # 13 real behavior tests
├── package.json          # Single package.json for frontend & dev orchestration
└── scripts/dev.js        # Starts FastAPI and Next.js concurrently
```

---

## Verification & Tests

### Backend Unit Tests
```bash
PYTHONPATH=backend pytest backend/tests/test_veridocs.py -v
```
*Result: 13 passed in ~0.5s.*

### Production Build
```bash
npm run build
```
*Result: Compiled successfully in ~3s.*

---

## Deployment

- **Frontend**: Deploy directly to [Vercel](https://vercel.com) by importing the repository root. Set `NEXT_PUBLIC_API_URL` to your backend URL.
- **Backend**: Deploy to [Render](https://render.com) using `backend/Dockerfile`. Fastembed weights (`bge-small-en-v1.5`) are pre-downloaded during Docker build so container cold-starts boot instantly under 30s.

---

## License

MIT
