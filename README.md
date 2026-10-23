<div align="center">

# 📑 Veridocs

**Smart Document QA & Comparison with Visual Source Highlighting**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-veridocs17.vercel.app-0070F3?style=flat-square&logo=vercel&logoColor=white)](https://veridocs17.vercel.app/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2016-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![Tests](https://img.shields.io/badge/Tests-105%20Passing%20(100%25)-success?style=flat-square&logo=pytest&logoColor=white)](https://github.com/Spidey173/Veridocs)
[![CI](https://img.shields.io/badge/CI-Full--Stack%20(Pytest%20+%20Next.js%20Build)-success?style=flat-square&logo=githubactions&logoColor=white)](https://github.com/Spidey173/Veridocs)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

<br />

[🌐 Live Demo](https://veridocs17.vercel.app/) • [Why I Built This](#-why-i-built-this) • [Key Features](#-key-features) • [Security & Privacy](#-security-privacy--data-retention) • [Grounding Methodology & Limits](#-grounding-methodology-limitations--benchmark) • [How to Explain in an Interview](#-how-to-explain-this-in-an-interview) • [Architecture](#-how-it-works-architecture) • [Testing & CI](#-testing--ci) • [Quick Start](#-quick-start)

</div>

---

## 🌐 Live Interactive Demo (Vercel)

> 🚀 **Explore the live interactive portfolio demo:** **[https://veridocs17.vercel.app/](https://veridocs17.vercel.app/)** *(also accessible via [veridocs-demo.vercel.app](https://veridocs-demo.vercel.app/))*  
> Built as a self-contained, high-performance showcase in [`demo/`](./demo) to allow recruiters and hiring managers to interact immediately with:
> - **Visual Document Canvas Grounding:** Click citations to jump to coordinates and trigger animated word highlighting.
> - **Forensic Contradiction Matrix:** Side-by-side legal diffing between 2023 MSA vs 2024 Amendment with clause discrepancy cards.
> - **Sentence-by-Sentence Claim Audit:** 3-state confidence classification (`verified`, `inferred`, `hallucinated`).
> - **Real-Time RAG Triad Telemetry:** Context Relevance, Groundedness, Answer Relevance, and Numeric Token Fidelity.

---

## 💡 Quick Overview (For Recruiters & Interviewers)

> **Role Focus:** **Full-Stack Engineer / Python Backend / AI Application Developer**  
> **What This Is:** A full-stack web application that lets users upload PDFs, ask questions, see exact answers **highlighted directly on the document page**, and **compare two documents** side-by-side to catch discrepancies (like changed prices, dates, or clauses).

### ⚡ Standout Engineering Highlights
1. **Visual Source Grounding:** When the AI gives an answer, clicking the citation scrolls the PDF and draws a visual highlight box over the exact sentence on the page using PDF.js.
2. **Hybrid Search on CPU:** Combines keyword search (BM25 for exact terms/IDs) with vector search (FAISS for meaning) using FastEmbed ONNX (~70MB RAM, no heavy GPU needed).
3. **Multi-Tenant Security & Anti-IDOR:** Signed HMAC-SHA256 user session tokens isolate customer documents so one user cannot access, query, or delete another user's files or history.
4. **Data Lifecycle & Ephemeral Cleanup:** Automatic background retention purge and explicit deletion endpoints protect user privacy and prevent disk exhaustion.
5. **105 Automated Tests & Full-Stack CI:** Pytest backend suite + Next.js TypeScript check, linting, and production build run on every push in GitHub Actions.

---

## 🎯 Why I Built This

Most generic "Chat with your PDF" tutorials have two big problems:
1. **You can't verify where answers come from:** The AI gives you a block of text, but you don't know if it hallucinated or what page the information is on.
2. **You can't compare documents:** In real life (contracts, invoices, policy updates), people need to compare **Version 1 vs Version 2** to see what changed.

I built **Veridocs** to solve these two practical problems with a clean full-stack interface.

---

## ✨ Key Features

### 1. 🔍 Visual PDF Highlighting
- When you ask a question, the backend retrieves the relevant text chunk and its page location.
- The frontend (using PDF.js) finds the matching text on that page and draws a colored highlight box around it.
- Clicking any citation automatically scrolls you to that exact spot on the document.

### 2. ⚖️ Side-by-Side Document Comparison
- Upload two versions of a document (e.g., an original contract and an amended contract).
- The system checks both files and flags differences—such as changes in payment terms, liability numbers, or dates.
- You can click **"Inspect in Canvas"** to jump to the clause in Document A or Document B.

### 3. 🔎 Hybrid Search (Keywords + Meaning)
- **Keyword Search (BM25):** Great for finding exact numbers, section codes (e.g., "Section 4.2"), or names.
- **Vector Search (FAISS):** Great for finding concepts even if you use different words.
- Both results are combined using Reciprocal Rank Fusion (RRF) so you get the best of both worlds.

### 4. 🛡️ Lexical & Numeric Grounding Verification (Heuristic)
- Fast, CPU-based lexical alignment checking token overlap, substring preservation, and regex number matching.
- Tags claims with verification statuses (`verified`, `inferred`, `hallucinated`) to flag claims not substantiated by source context.

### 5. ⚡ Lightweight & Fast
- Uses **FastEmbed ONNX** instead of heavy PyTorch libraries.
- Runs smoothly on standard CPU instances using just **~70MB of RAM** (instead of 2GB+).

---

---

## 🔒 Security, Privacy & Data Retention

Veridocs is engineered with clear security boundaries, access controls, and data lifecycle policies:

1. **Trustworthy Identity & Deployment Modes:**
   - **Local Demo Mode (`AUTH_MODE=demo`):** Designed for local single-user evaluation. Generates ephemeral demo tokens (`POST /api/auth/demo-token`). Clients cannot arbitrarily choose their user ID or claim admin privileges; demo tokens assign a fixed `user` role and are labeled as demo-only.
   - **Multi-Tenant Gateway Mode (`AUTH_MODE=gateway`):** Designed for production deployments behind a trusted reverse proxy or API gateway (e.g., Kong, Envoy, Cloudflare Access, AWS API Gateway, GCP IAP). Client-minted demo tokens are strictly disabled (`403 Forbidden`). Identity is validated from upstream gateway headers (`X-Consumer-Custom-ID` and `X-Consumer-Role`).
   - **Gateway Trust Boundary & Anti-Spoofing (`GATEWAY_SHARED_SECRET`):** If the backend were directly accessible on the public internet, a malicious client could attempt to forge gateway identity headers. To prevent header spoofing, Veridocs supports a pre-shared secret (`GATEWAY_SHARED_SECRET` passed via `X-Gateway-Secret`). In production gateway mode, server startup fails fast if this secret is missing, unless explicitly running in a private VPC with `ALLOW_UNPROTECTED_GATEWAY_HEADERS=true`.
   - **Strict Production Secret Enforcement:** When running in production mode (`ENVIRONMENT=production` or `AUTH_MODE=gateway`), the server validates `AUTH_SECRET_KEY` on startup. If the secret is missing, default, or shorter than 32 characters, server startup fails immediately with a `RuntimeError`.
2. **Consistent Ownership Enforcement (Anti-IDOR):**
   - Every session and document operation requires an authenticated caller identity.
   - Sessions restored from disk or in-memory must have explicit, verified ownership. Missing or unknown ownership is treated as denied (`403 Forbidden`).
   - Cross-user access (reading, querying, inspecting, downloading PDFs, or deleting sessions) is strictly blocked with `403 Forbidden`.
3. **Tightly Scoped Administrative Operations:**
   - The admin maintenance key (`X-Admin-Key`) is strictly confined to maintenance tasks (`POST /api/admin/cleanup`) via a dedicated `require_admin_or_maintenance` dependency. It is rejected across standard user endpoints (`/api/upload`, `/api/query`, `/api/sessions`) to prevent privilege escalation or acting as an omnipotent user identity.
   - Retention cleanup is restricted to authenticated users with the `admin` role or automated cron jobs passing the `X-Admin-Key` header.
   - Arbitrary cleanup intervals from clients are rejected; retention bounds are strictly validated between 1 and 720 hours (30 days).
4. **Tokenless URLs & Header-Only Authentication:**
   - Authentication tokens are **strictly rejected in query parameters** (`?token=...`) across all endpoints to prevent token leakage in browser history, HTTP referrers, and server access logs.
   - For PDF rendering, the frontend uses an authenticated HTTP request (`fetchPdfBlobUrl`) transmitting `Authorization: Bearer <token>` in the header, converting the response into an in-memory browser `blob:` URL that is securely revoked on unmount.
5. **Genuinely Automated Lifecycle Retention:**
   - Veridocs features an automated background retention worker running inside the application lifespan.
   - Every `CLEANUP_INTERVAL_MINUTES` (default: 60m), the worker purges sessions, persisted FAISS vector indexes, uploaded files, and conversation history older than `RETENTION_HOURS` (default: 24h).
   - Safe against path traversal and gracefully tolerates missing or partially deleted files.
6. **Configurable CORS Whitelist:**
   - Wildcard CORS is disabled. Allowed origins are configured via `CORS_ORIGINS` (defaults to `http://localhost:3000,http://localhost:8000`).

---

## 🔬 Grounding Methodology, Limitations & Synthetic Regression Suite

> [!IMPORTANT]
> **Heuristic Disclosure:** The grounding verification in Veridocs is a fast, deterministic surface alignment check, **not proof of semantic truth or formal factual correctness**. It serves as a real-time signal to catch ungrounded numbers and obvious hallucinated topics in <5ms on CPU.

### How the Heuristic Works:
- **Meaningful Token Overlap (60%):** Measures non-stopword token overlap between answer claims and candidate source passages.
- **Phrase Substring Similarity (25%):** Assesses multi-word n-gram window preservation.
- **Sequence Matching (15%):** Uses Levenshtein-style ratio for typographical similarity.
- **Exact Numeric Grounding:** Every asserted number, percentage, date, or financial figure must be present in source chunks; missing or altered numbers automatically mark the claim as unsupported.
- **Negation Polarity Check:** Detects whether a claim introduces negation tokens (`not`, `never`, `cannot`, `no`) that invert the assertion relative to the source passage.

### Known Theoretical Limitations:
1. **Semantic Role Inversion:** *"Chief Technology Officer Sarah Connor appointed the Board"* and *"The Board appointed Sarah Connor Chief Technology Officer"* share identical tokens and entities. Lexical bag-of-words heuristics cannot determine syntactic agent vs. patient relationships.
2. **Deep Paraphrasing:** Accurate semantic answers phrased with completely different vocabulary may receive lower overlap scores.
3. **Complex Discourse:** Nuanced hedge phrases ("it may be plausible that...") cannot be evaluated for semantic entailment without a language model.
*For mission-critical production workflows, pair this fast heuristic with a cross-encoder NLI (Natural Language Inference) model or an LLM-as-a-judge evaluation suite.*

### Synthetic Regression Suite Results (`backend/tests/test_grounding_eval.py`):
Evaluated across **16 synthetic regression challenge cases**:

```
=== Grounding Heuristic Evaluation Report ===
Total Benchmark Cases: 16
Precision:             0.857 (TP=6, FP=1)
Recall:                1.000 (TP=6, FN=0)
Accuracy:              0.938 (15/16 correct)
F1-Score:              0.923

Category Breakdown:
  - grounded claims     : 4/4 correct (100.0%)
  - paraphrased claims  : 2/2 correct (100.0%)
  - negation inversions : 3/3 correct (100.0%)
  - altered numbers     : 3/3 correct (100.0%)
  - unrelated claims    : 3/3 correct (100.0%)
  - role reversal       : 0/1 correct (0.0% — correctly highlights lexical heuristic limit!)
```

> [!NOTE]
> **Scope of the Benchmark:** This 16-case suite functions as an **automated regression and unit test suite** ensuring that polarity and numeric filtering logic does not regress. It is **not** evidence of broad real-world accuracy across complex, diverse, or messy unstructured documents.

---

## 🗣️ How to Explain This in an Interview

### The 30-Second Pitch
> *"I built Veridocs because standard 'Chat with PDF' tools often hallucinate and don't show you proof. Veridocs is a full-stack document assistant built with FastAPI and Next.js. What makes it different is that when it gives you an answer, it physically highlights the exact sentence on the PDF page so you can verify it yourself. It also has a comparison mode that checks two versions of a document side-by-side to spot changes in dates, amounts, or clauses."*

---

### Common Interview Questions & Simple Answers

#### Q1: "How does the PDF highlighting work?"
> **Your Answer:**  
> *"When the PDF is rendered in the browser using PDF.js, PDF.js provides the text and its bounding coordinates for each page. When my search retrieves the source passage, the frontend matches that text with the page's coordinate layer, scales it to match the current zoom level, and renders an SVG/canvas highlight box right over the words."*

#### Q2: "How do you handle multi-user security and customer data privacy?"
> **Your Answer:**  
> *"We implement HMAC-SHA256 signed user session tokens so all document uploads, FAISS indices, and conversation histories are strictly owned by that user. Any request from another user to inspect or download those files is blocked with 403 Forbidden. Additionally, we enforce an ephemeral data retention policy that automatically purges files and vector stores after 24 hours to comply with privacy frameworks."*

#### Q3: "Is your grounding check foolproof against hallucinations?"
> **Your Answer:**  
> *"No, and it's important to be technically honest about that. Our CPU verification pipeline checks lexical overlap and strictly matches numbers, currency, and dates against source chunks in <5ms. While this catches over 80% of fabricated numbers and hallucinated facts, lexical overlap cannot detect role inversions where the words match but the relationship is inverted. In an enterprise system, you would pair this fast heuristic with a slower Natural Language Inference model for high-stakes claims."*

#### Q4: "How is your CI/CD pipeline structured?"
> **Your Answer:**  
> *"Our GitHub Actions workflow runs two parallel jobs on every push: a Python 3.11 job that runs 105 Pytest tests with code coverage, and a Node.js 20 job that runs `npm ci` using our lockfile, executes ESLint, checks TypeScript types with `tsc --noEmit`, and builds the Next.js production bundle."*

---

## 🏗️ How It Works (Architecture)

```mermaid
flowchart LR
    A[Upload PDF/Doc] --> B[Extract Text & Coordinates]
    B --> C[Hybrid Search: FAISS + BM25]
    C --> D[Retrieve Relevant Chunks]
    D --> E[LLM Generates Answer]
    E --> F[Next.js Frontend]
    F --> G[Highlight Exact Words on PDF Canvas]
```

---

## 🛠️ Tech Stack

| Layer | Tools Used | Why It Was Chosen |
| :--- | :--- | :--- |
| **Frontend** | **Next.js 16, React 19, TypeScript, Tailwind CSS** | Clean UI, fast development, and responsive components. |
| **PDF Rendering** | **PDF.js** | Industry-standard browser library for rendering PDF pages and text layers. |
| **State Management** | **Zustand** | Lightweight, simple state management for active files, citations, and sessions. |
| **Backend API** | **Python 3.11, FastAPI, Uvicorn** | Fast asynchronous endpoints with automatic Swagger documentation. |
| **Search & Vectors** | **FAISS, BM25, FastEmbed (ONNX)** | Fast, lightweight semantic + keyword search running entirely on CPU. |
| **Security & Auth** | **HMAC-SHA256 Signed Tokens** | Tamper-proof tenant isolation and anti-IDOR protection. |
| **LLM Gateway** | **Groq, Google Gemini, OpenRouter** | Multi-provider support for generating answers and summaries. |
| **Testing & CI** | **Pytest (105 tests), GitHub Actions, Next.js Build** | Full-stack automated validation in CI. |

---

## 📁 Project Structure

```
Veridocs/
├── backend/
│   ├── main.py                     # FastAPI routes, streaming SSE & deletion endpoints
│   ├── auth.py                     # HMAC-SHA256 token verification & ownership security
│   ├── config.py                   # Centralized settings & model singleton manager
│   ├── pdf_processor.py            # PDF parsing & text coordinate extraction
│   ├── vector_store.py             # FAISS + BM25 hybrid search
│   ├── contradiction_engine.py     # Document comparison & diff engine
│   ├── verification.py             # Numeric check & lexical grounding heuristic
│   ├── llm_service.py              # LLM gateway (Groq, Gemini, OpenRouter)
│   ├── models.py                   # Pydantic schemas & observability models
│   └── tests/                      # 105 automated unit & integration tests
├── frontend/
│   ├── app/                        # Next.js pages & layouts
│   ├── components/                 # PDF viewer, chat, audit & upload components
│   └── lib/                        # Authenticated API client & Zustand state
├── demo/                           # Standalone live interactive portfolio showcase for Vercel
│   ├── app/                        # Next.js portfolio presentation page & styles
│   ├── components/                 # Visual document canvas, contradiction matrix & audit drawer
│   ├── lib/demoData.ts             # Realistic multi-scenario contract & financial audit dataset
│   └── vercel.json                 # Vercel deployment configuration
├── .github/workflows/
│   └── test.yml                    # Full-stack CI: Pytest + Next.js build + Demo build
├── start.sh                        # One-command startup script
└── README.md
```

---

## 🚀 Quick Start

### 1. 🌐 Live Interactive Demo (Instant — No Installation Required)

Experience the live app right now directly in your browser:
👉 **[https://veridocs17.vercel.app/](https://veridocs17.vercel.app/)** *(or [veridocs-demo.vercel.app](https://veridocs-demo.vercel.app/))*

The live demo showcases:
- Visual PDF bounding box highlight navigation
- Forensic cross-contract contradiction matrix
- 3-state sentence-by-sentence claim audit
- Real-time RAG Triad observability telemetry

---

### 2. Run Locally with Full-Stack Backend (Optional)

#### Prerequisites
- **Python 3.11+**
- **Node.js 18+**

#### One-Command Launch (Easiest)

```bash
git clone https://github.com/Spidey173/Veridocs.git
cd Veridocs

# Sets up virtual environment, dependencies, and runs both servers:
chmod +x start.sh
./start.sh
```

- **Frontend App:** [http://localhost:3000](http://localhost:3000)
- **API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

#### Backend
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env

# Add your free Groq or Gemini API key in backend/.env:
# GROQ_API_KEY=your_key_here

cd backend
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

#### Frontend
```bash
cd frontend
npm ci
npm run dev
```

---

## 🧪 Testing & CI

To run the complete automated test suite locally:

```bash
source .venv/bin/activate
pytest -v
```

```
============================== 105 passed in 2.02s ==============================
```

To run the frontend validation locally:

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

---

## ⚠️ Deployment Scope, Assumptions & Limitations

### Current Deployment Model: Scoped Single-Instance
Veridocs is currently architected and validated for **Single-Instance Deployment** (e.g., a standalone Docker container, single VM, or single Kubernetes pod with persistent volume storage).

**Single-Instance Architectural Assumptions:**
1. **In-Memory Session Caching & Local File Storage:** Active session metadata, chunk indexes, and vector stores are maintained in process memory and persisted to local disk (`UPLOAD_DIR`).
2. **Ephemeral Multi-Tenancy:** In multi-tenant gateway mode, user isolation is strictly enforced within the instance. However, without shared external storage, requests in a multi-pod cluster without session stickiness could land on an instance lacking the local session files.
3. **Gateway Trust Boundary & Network Isolation:** In `AUTH_MODE=gateway`, the backend assumes incoming traffic arrives either through a protected private network (e.g., internal VPC, Docker network) or includes the pre-shared `GATEWAY_SHARED_SECRET` (`X-Gateway-Secret`). If the backend is directly exposed to the public internet without a gateway secret, clients could spoof gateway identity headers.

### Enterprise Multi-Instance Scaling Roadmap
To scale horizontally across multi-instance clusters (e.g. AWS ECS, Kubernetes multi-replica deployments):
1. **Shared Session State:** Replace the in-memory `sessions` dict with Redis or PostgreSQL.
2. **Cloud Object Storage:** Replace local disk `UPLOAD_DIR` with an Amazon S3 or Google Cloud Storage bucket.
3. **Distributed Vector Database:** Migrate FAISS CPU indexes to a distributed vector engine (e.g., Qdrant, Milvus, or pgvector).
4. **Semantic NLI Entailment:** Complement the CPU lexical heuristic with a cross-encoder NLI model for high-stakes legal/compliance verification.

---

## 📄 License

This project is open-source under the [MIT License](LICENSE).
