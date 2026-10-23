<div align="center">

# 📑 Veridocs

**Smart Document QA & Comparison with Visual Source Highlighting**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2016-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![Tests](https://img.shields.io/badge/Tests-98%20Passing%20(100%25)-success?style=flat-square&logo=pytest&logoColor=white)](https://github.com/Spidey173/Veridocs)
[![CI](https://img.shields.io/badge/CI-Full--Stack%20(Pytest%20+%20Next.js%20Build)-success?style=flat-square&logo=githubactions&logoColor=white)](https://github.com/Spidey173/Veridocs)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

<br />

[Why I Built This](#-why-i-built-this) • [Key Features](#-key-features) • [Security & Privacy](#-security-privacy--data-retention) • [Grounding Methodology & Limits](#-grounding-methodology--limitations) • [How to Explain in an Interview](#-how-to-explain-this-in-an-interview) • [Architecture](#-how-it-works-architecture) • [Testing & CI](#-testing--ci) • [Quick Start](#-quick-start)

</div>

---

## 💡 Quick Overview (For Recruiters & Interviewers)

> **Role Focus:** **Full-Stack Engineer / Python Backend / AI Application Developer**  
> **What This Is:** A full-stack web application that lets users upload PDFs, ask questions, see exact answers **highlighted directly on the document page**, and **compare two documents** side-by-side to catch discrepancies (like changed prices, dates, or clauses).

### ⚡ Standout Engineering Highlights
1. **Visual Source Grounding:** When the AI gives an answer, clicking the citation scrolls the PDF and draws a visual highlight box over the exact sentence on the page using PDF.js.
2. **Hybrid Search on CPU:** Combines keyword search (BM25 for exact terms/IDs) with vector search (FAISS for meaning) using FastEmbed ONNX (~70MB RAM, no heavy GPU needed).
3. **Multi-Tenant Security & Anti-IDOR:** Signed HMAC-SHA256 user session tokens isolate customer documents so one user cannot access, query, or delete another user's files or history.
4. **Data Lifecycle & Ephemeral Cleanup:** Automatic 24-hour retention purge and explicit deletion endpoints protect user privacy and prevent disk exhaustion.
5. **98 Automated Tests & Full-Stack CI:** Pytest backend suite + Next.js TypeScript check, linting, and production build run on every push in GitHub Actions.

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

## 🔒 Security, Privacy & Data Retention

Veridocs is engineered with security and tenant isolation principles:

1. **Authentication & Tenant Isolation:**
   - Every client request requires a signed HMAC-SHA256 session token (`Authorization: Bearer <token>` or `?token=<token>`).
   - Sessions and uploaded documents are tagged with an `owner_id`. Any attempt by User B to query, view, download, or delete User A's session results in `403 Forbidden` (Insecure Direct Object Reference protection).
2. **Configurable CORS Whitelist:**
   - Wildcard CORS is disabled. Allowed origins are configured via the `CORS_ORIGINS` environment variable (defaults to `http://localhost:3000,http://localhost:8000`).
3. **Data Lifecycle & Ephemeral Retention:**
   - **Explicit Deletion:** Users can delete entire sessions (`DELETE /api/sessions/{id}`) or individual documents (`DELETE /api/sessions/{id}/documents/{filename}`). Deletion purges disk files, FAISS vector indexes, and conversation history.
   - **Path Traversal Protection:** All file deletion operations resolve paths strictly against the canonical upload root; traversal sequences (`../`) are safely rejected.
   - **Automated Retention Purge:** Background maintenance cleans up sessions and orphaned files older than `RETENTION_HOURS` (default: 24h).
4. **Gateway API Key Protection (Optional):**
   - For enterprise gateway deployments, setting `REQUIRE_API_KEY=true` enforces an `X-API-Key` check on all API routes.

---

## 🔬 Grounding Methodology & Limitations

> [!IMPORTANT]
> **Heuristic Disclosure:** The grounding verification in Veridocs is a fast, deterministic surface alignment check, **not proof of semantic truth or formal factual correctness**.

### How the Heuristic Works:
- **Meaningful Token Overlap (60%):** Measures non-stopword token overlap between the answer claim and candidate source passages.
- **Phrase Substring Similarity (25%):** Assesses multi-word n-gram window preservation.
- **Sequence Matching (15%):** Uses Levenshtein-style ratio for typographical similarity.
- **Exact Numeric Grounding:** Every asserted number, percentage, date, or financial figure must be present in source chunks; missing or altered numbers automatically mark the claim as unsupported.

### Known Limitations:
1. **Semantic Role Inversion:** *"Company A acquired Company B"* and *"Company B acquired Company A"* share 100% of tokens and numbers, but have opposite factual meanings.
2. **Paraphrasing Nuance:** Highly accurate answers phrased with completely different vocabulary may receive lower overlap scores.
3. **Negation:** Simple bag-of-words heuristics cannot verify complex inverted clauses.
*For mission-critical production legal or medical workflows, this heuristic should be paired with an NLI (Natural Language Inference) model or an LLM-as-a-judge pipeline.*

### Deterministic Benchmark Results (`backend/tests/test_grounding_eval.py`):
```
Total Test Cases: 10
Precision:        1.000 (TP=4, FP=0)
Recall:           1.000 (TP=4, FN=0)
Accuracy:         1.000
F1-Score:         1.000
Category Breakdown:
  - grounded claims     : 4/4 correct (100.0%)
  - altered numbers     : 3/3 correct (100.0%)
  - subtle unsupported  : 3/3 correct (100.0%)
```

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
> *"Our GitHub Actions workflow runs two parallel jobs on every push: a Python 3.11 job that runs 98 Pytest tests with code coverage, and a Node.js 20 job that runs `npm ci` using our lockfile, executes ESLint, checks TypeScript types with `tsc --noEmit`, and builds the Next.js production bundle."*

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
| **Testing & CI** | **Pytest (98 tests), GitHub Actions, Next.js Build** | Full-stack automated validation in CI. |

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
│   └── tests/                      # 98 automated unit & integration tests
├── frontend/
│   ├── app/                        # Next.js pages & layouts
│   ├── components/                 # PDF viewer, chat, audit & upload components
│   └── lib/                        # Authenticated API client & Zustand state
├── .github/workflows/
│   └── test.yml                    # Full-stack CI: Pytest + Next.js build
├── start.sh                        # One-command startup script
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+**
- **Node.js 18+**

### 1. One-Command Launch (Easiest)

```bash
git clone https://github.com/Spidey173/Veridocs.git
cd Veridocs

# Sets up virtual environment, dependencies, and runs both servers:
chmod +x start.sh
./start.sh
```

- **Open the App:** [http://localhost:3000](http://localhost:3000)
- **API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

### 2. Manual Setup (Optional)

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
============================== 98 passed in 5.90s ==============================
```

To run the frontend validation locally:

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

---

## ⚠️ Remaining Production Roadmap & Limitations

While Veridocs now includes strong multi-tenant security, safe data retention, and full-stack CI, enterprise production deployments should consider:
1. **Multi-Instance Shared Persistence:** For horizontally auto-scaled clusters across multiple container nodes (e.g., AWS ECS or Kubernetes), local disk storage (`UPLOAD_DIR`) should be backed by an S3/GCS bucket, and in-memory session metadata should be backed by a shared Redis or PostgreSQL instance.
2. **Semantic NLI Verification:** For critical legal or financial compliance, pair the existing <5ms lexical grounding check with an NLI model or an LLM-as-a-judge entailment evaluator.

---

## 📄 License

This project is open-source under the [MIT License](LICENSE).
