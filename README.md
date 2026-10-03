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

## ✨ Features

- **📄 Multi-Document Support:** Upload and search across multiple PDF, DOCX, and TXT files simultaneously in a single workspace.
- **🎯 Interactive Page Citations:** Click any citation pill (e.g., `[Page 3]`) in the chat to instantly jump to that exact page in the PDF canvas.
- **⚡ Two-Stage Hybrid Retrieval:**
  - **BM25 Lexical Search:** Matches exact keywords, acronyms, and numbers.
  - **FAISS Vector Search:** Matches meaning and semantics using dense embeddings.
  - **Reciprocal Rank Fusion (RRF):** Blends keyword and semantic results to find the most accurate passages.
- **🧠 Cross-Encoder Re-Ranking:** Re-scores retrieved candidate passages using a cross-encoder model to filter out irrelevant text before passing it to the LLM.
- **🛡️ 3-State Claim Verification (Fact-Checking):**
  - 🟢 **Verified:** Directly backed by the text in the document.
  - 🟡 **Inferred:** Logically derived or summarized from the context.
  - 🔴 **Unsupported:** Warns the user if the claim lacks direct support in the source.
- **📊 Document Insights:** Automatically generates an executive summary and extracts key entities like financial amounts (`$2.5M`), dates, and organizations right after uploading.
- **⚡ Fast & Lightweight:** Uses CPU-friendly FastEmbed ONNX models (~70MB RAM, zero PyTorch overhead) so it runs smoothly even on free-tier cloud containers.
- **🔄 Flexible LLM Support:** Easily connect with free API keys from **Google Gemini**, **Groq**, or **OpenRouter**.

---

## 🏗️ How It Works

```
1. Upload Document   ──► Extract text and split into clean, semantic chunks
2. Hybrid Search     ──► Retrieve top candidate chunks using BM25 + FAISS
3. Re-Ranking        ──► Cross-encoder ranks and filters down to the top relevant chunks
4. LLM Generation    ──► Context-injected prompt generates answer with citations
5. Fact Verification ──► Claims are verified against source text (Verified / Inferred / Unsupported)
6. Instant View      ──► User sees answer, clicks citation, and PDF jumps to target page
```

---

## 🛠️ Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, Lucide Icons |
| **State & Viewer** | Zustand, PDF.js canvas viewer (with local Blob URL rendering) |
| **Backend** | Python 3.11, FastAPI, Uvicorn, Pydantic v2 |
| **Search & AI** | FAISS (vector search), BM25 (keyword search), FastEmbed ONNX (embeddings & cross-encoder) |
| **LLM Providers** | Google Gemini 2.5 Flash, Groq (Qwen/Llama), OpenRouter |
| **Testing** | Pytest, Pytest-Asyncio, Pytest-Cov (78 automated tests) |

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

- **Test Results:** 78 / 78 passing (100%)
- **Test Coverage:** ~82%
- **Zero External Calls:** All tests use deterministic local mocks, running in under 1 second without consuming any API credits.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
