<div align="center">

# 📑 Veridocs

**An Enterprise Multi-PDF Q&A platform with two-stage retrieval (FAISS + Cross-Encoder), citation grounding, and hallucination verification.**

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Frontend-Next.js%2016-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-78%20Passing-success?style=flat-square)](https://github.com/Spidey173/Veridocs)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## 💡 What Problem Does This Solve?

Standard RAG (Retrieval-Augmented Generation) applications often suffer from two common problems:
1. **Low Retrieval Precision:** Single-stage vector search frequently retrieves irrelevant context, polluting the LLM prompt.
2. **Hallucinations & Lack of Source Traceability:** Users cannot easily verify whether the LLM generated accurate information or which page it came from.

**Veridocs** addresses these challenges by introducing a **two-stage retrieval pipeline (FAISS + Cross-Encoder)**, **exact page-level source citations**, and an **automated post-generation verification layer** to audit claims against source text.

---

## 🚀 Key Features

* **📄 Multi-PDF Q&A with Page-Level Citations**  
  Ingests multiple documents simultaneously and attaches `[Page X]` citations to generated answers so users can instantly verify statements against the source document.

* **⚡ Two-Stage Retrieval (FAISS + Cross-Encoder Reranking)**  
  Performs fast dense vector search via FAISS (`all-MiniLM-L6-v2`) to retrieve top candidate chunks, then refines and re-scores them using a Cross-Encoder (`ms-marco-MiniLM-L-6-v2`) to ensure only the most relevant context reaches the LLM.

* **🛡️ Factual Grounding & Hallucination Verification**  
  Splits generated responses into individual claims and checks sequence/n-gram overlap against retrieved source passages, computing a grounding confidence score to flag unsupported claims.

* **🔄 Swappable Multi-LLM Backend**  
  Built with a unified adapter interface supporting **Google Gemini**, **Groq**, and **OpenRouter**, switchable via `.env` configuration without changing application code.

---

## 🏗️ How It Works (Pipeline)

```
1. Document Ingestion    ──► Text extraction with page tracking (PyPDF / EasyOCR)
2. Chunking & Indexing   ──► Recursive text chunking + FAISS dense vector store
3. Query & Retrieval     ──► Top-K candidate chunks retrieved via vector similarity
4. Cross-Encoder Rerank  ──► Re-scores (query, chunk) pairs to select top relevant context
5. LLM Answer Generation ──► Context-injected prompt sent to LLM (Gemini/Groq/OpenRouter)
6. Grounding Validation  ──► Post-generation claim verification & page citation attachment
```

---

## 🧠 Key Design Decisions

| Decision | Why It Was Chosen |
| :--- | :--- |
| **FAISS Vector Store** | Lightweight, runs in-memory/locally, eliminating external database dependencies for fast prototyping and low latency. |
| **Cross-Encoder Reranker** | Bi-encoders compare embeddings independently. Cross-Encoders attend to both query and passage simultaneously, offering significantly higher ranking precision before LLM generation. |
| **Claim-Level Grounding Check** | Rather than blind trust in LLM outputs, string/n-gram overlap scoring verifies if each statement exists in the retrieved source text. |
| **Modular LLM Gateway** | Decoupled LLM service allows zero-code-change switching across different API providers (Gemini, Groq, OpenRouter) to balance speed and cost. |

---

## 📁 Project Structure

```
Veridocs/
├── backend/
│   ├── config.py              # Application settings & model registry
│   ├── conversation.py        # Chat session management
│   ├── insights_engine.py     # Document summary & entity extraction
│   ├── llm_service.py         # Multi-LLM provider gateway
│   ├── main.py                # FastAPI endpoints & static routing
│   ├── models.py              # Pydantic schemas
│   ├── pdf_processor.py       # PDF extraction & page-level chunking
│   ├── reranker.py            # Cross-Encoder reranking pipeline
│   ├── vector_store.py        # FAISS vector store integration
│   ├── verification.py        # Factual grounding & citation engine
│   ├── requirements.txt       # Backend dependencies
│   ├── pytest.ini             # Pytest configuration
│   └── tests/                 # Automated Pytest suite (78 tests, ~86% coverage)
│       ├── conftest.py            # Shared fixtures & mock providers
│       ├── test_api_endpoints.py  # FastAPI integration & SSE stream tests
│       ├── test_config.py         # Settings & model registry tests
│       ├── test_conversation.py   # Multi-turn memory & LRU cache tests
│       ├── test_insights_engine.py# Entity extraction & summary tests
│       ├── test_llm_service.py    # Multi-provider LLM gateway tests
│       ├── test_models.py         # Pydantic schemas validation
│       ├── test_pdf_processor.py  # Text cleaning & section parsing
│       ├── test_reranker.py       # Cross-Encoder reranking tests
│       ├── test_vector_store.py   # BM25 + FAISS hybrid RRF tests
│       └── test_verification.py   # Claim-level grounding & citations
├── frontend/
│   ├── app/                   # Next.js App Router
│   ├── components/            # UI components (chat, viewer, upload)
│   ├── lib/                   # API client & Zustand state store
│   └── package.json           # Frontend dependencies
└── README.md
```

---

## ⚡ Quick Start

### 1. Backend Setup

```bash
cd backend
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Add your API key (GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY)
uvicorn main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The app will be running at [http://localhost:3000](http://localhost:3000).

---

## 🧪 Automated Testing

Veridocs includes a full automated test suite covering unit logic and FastAPI endpoint integration tests.

```bash
# Run all tests
pytest

# Run with verbose output and test coverage report
pytest --cov=backend --cov-report=term-missing
```

* **Test Suite:** 78 automated tests (0 external API calls required during test runs).
* **Coverage:** ~86% overall code coverage.
* **Continuous Integration:** Automated GitHub Actions workflow on every push/PR via `.github/workflows/test.yml`.

---

## 📄 License

This project is open-source under the [MIT License](LICENSE).
