<div align="center">

# 📑 Veridocs

**An AI-powered Document Intelligence platform that lets you chat with your documents with page-level citations and automated fact-checking.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2015-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![Tests](https://img.shields.io/badge/Tests-78%20Passing-success?style=flat-square&logo=pytest&logoColor=white)](https://github.com/Spidey173/Veridocs)
[![License](https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square)](LICENSE)

</div>

---

## 📌 Overview

When using standard AI document search (RAG), users often face two major issues:
1. **Hallucinations:** The AI answers confidently, but you cannot easily tell if the information was made up or actually mentioned in the document.
2. **Missing Citations:** You get an answer, but you still have to manually search through a 50-page PDF to find the exact page or paragraph.

**Veridocs** solves this by combining **hybrid search (keywords + semantics)** with a **neural cross-encoder re-ranker**, **clickable page citations**, and an **automatic fact-checking engine** that grades whether claims are verified, inferred, or unsupported.

---

## ✨ Features & Technical Implementation

- **📄 Multi-Document Ingestion:** Parses and indexes PDF, DOCX, and TXT files using `pypdf`, `python-docx`, and LangChain recursive character chunking with metadata preservation (document title, page number, chunk index).
- **🎯 Interactive Page Citations:** Clickable citation badges (e.g. `[Page 3]`) integrated with the client-side PDF.js canvas viewer to jump directly to the cited page.
- **⚡ Two-Stage Hybrid Retrieval:**
  - **BM25 Lexical Index:** In-memory keyword scoring for exact matches, technical acronyms, and figures.
  - **FAISS Vector Index:** Dense similarity search using `sentence-transformers/all-MiniLM-L6-v2` embeddings via ONNX runtime.
  - **Reciprocal Rank Fusion (RRF):** Merges rank lists ($k=60$) from both sparse and dense retrievers to produce candidate passages.
- **🧠 Cross-Encoder Re-Ranking:** Re-scores the top retrieved candidate chunks using `ms-marco-MiniLM-L-6-v2` cross-encoder scoring to filter out low-relevance passages before LLM context construction.
- **🛡️ 3-State Claim Grounding & Verification:**
  - Evaluates generated responses sentence-by-sentence using a combination of token overlap (Jaccard), fuzzy sequence matching, and strict numeric consistency checks.
  - Classifies claims as 🟢 **Verified** (high lexical similarity + matching numerical entities), 🟡 **Inferred** (conceptual overlap), or 🔴 **Unsupported** (flagging ungrounded claims or hallucinated figures).
- **📊 Heuristic Document Insights:** Extracts structured entities (monetary amounts, dates, percentages, organizations) via regular expressions and generates high-level summaries immediately upon document upload.
- **⚡ Lightweight CPU Inference:** Leverages FastEmbed ONNX runtime (~70MB memory footprint, zero heavy PyTorch dependencies) to ensure responsive embedding generation even on resource-constrained containers.
- **🔄 Multi-Provider LLM Gateway:** Configurable support for Google Gemini, Groq (Qwen / Llama), OpenRouter, and GitHub Models.

---

## 🏗️ Retrieval & Generation Pipeline

```
1. Ingestion       ──► Parse document -> Recursive text chunking -> Assign page & chunk metadata
2. Hybrid Search   ──► Dual retrieval via BM25 (keyword) + FAISS (dense embeddings)
3. Rank Fusion     ──► Merge candidate rankings using Reciprocal Rank Fusion (RRF)
4. Re-Ranking      ──► Cross-encoder model scores and trims candidates to top-K
5. Generation      ──► Context-injected prompt sent to LLM with citation constraints
6. Claim Grounding ──► Post-generation verification scores sentence overlap and flags unverified numbers
7. UI Presentation ──► Render formatted response with interactive page citation pills
```

---

## 🛠️ Tech Stack

| Layer | Technologies | Role in Project |
| :--- | :--- | :--- |
| **Frontend** | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS | Modern dashboard, responsive layouts, SSE stream consumption |
| **State & Viewer** | Zustand, PDF.js | Local state management and in-browser canvas PDF rendering |
| **Backend** | Python 3.11, FastAPI, Uvicorn, Pydantic v2 | High-performance asynchronous REST and SSE streaming API |
| **Search & AI** | FAISS, Custom BM25, FastEmbed ONNX | Hybrid retrieval, RRF ranking, and neural cross-encoder re-ranking |
| **LLM Gateway** | Google Gemini, Groq, OpenRouter, GitHub Models | Flexible model routing and context-grounded response generation |
| **Testing** | Pytest, Pytest-Asyncio, Pytest-Cov | Automated unit and integration testing suite |

---

## 📁 Project Structure

```
Veridocs/
├── backend/
│   ├── config.py              # Configuration & model registry singleton
│   ├── conversation.py        # Multi-turn chat session memory
│   ├── insights_engine.py     # Summary generation & entity extraction
│   ├── llm_service.py         # Multi-provider LLM gateway
│   ├── main.py                # FastAPI REST & SSE streaming endpoints
│   ├── models.py              # Pydantic data schemas
│   ├── pdf_processor.py       # PDF, DOCX, and TXT parsing & chunking
│   ├── reranker.py            # Neural Cross-Encoder re-ranker
│   ├── vector_store.py        # FAISS vector store & BM25 hybrid search
│   ├── verification.py        # 3-state claim grounding & fact-checking
│   ├── requirements.txt       # Python dependencies
│   └── tests/                 # 78 automated unit & integration tests
├── frontend/
│   ├── app/                   # Next.js App Router (layout, landing page)
│   ├── components/            # UI components (Chat, PDF viewer, Insights, Upload)
│   ├── lib/                   # API client & Zustand state store
│   └── package.json           # Frontend dependencies
├── render.yaml                # Render cloud deployment blueprint
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+**
- **Node.js 18+**

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
```

Open `.env` and add your free API key (e.g. Gemini or Groq):
```env
LLM_PROVIDER=google
GOOGLE_API_KEY=your_gemini_api_key_here
```

Start the backend server:
```bash
uvicorn main:app --reload --port 8000
```
API docs will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

### 2. Frontend Setup

```bash
# In a new terminal, navigate to the frontend directory
cd frontend

# Install packages
npm install

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🧪 Testing

The backend includes a comprehensive automated test suite with **78 tests** covering all parsing, retrieval, re-ranking, verification, and API endpoint logic.

```bash
# Run pytest from the root or backend directory
pytest

# Run with test coverage report
pytest --cov=backend --cov-report=term-missing
```

- **Test Suite:** 78 unit & integration tests covering parsing, retrieval fusion, re-ranking, claim verification, and API endpoints.
- **Mocked External Services:** Tests leverage deterministic mocks for LLM and embedding pipelines, enabling fast local execution without external API dependencies or network latency.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
