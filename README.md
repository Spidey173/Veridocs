# 📑 Veridocs — Forensic Document AI & Contradiction Diff Engine

[![CI Pipeline](https://github.com/Spidey173/Veridocs/actions/workflows/ci.yml/badge.svg)](https://github.com/Spidey173/Veridocs/actions)
[![Tests](https://img.shields.io/badge/Tests-107%20Passed-brightgreen?style=flat-square&logo=pytest)](backend/tests/)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](backend/)
[![Frontend](https://img.shields.io/badge/Frontend-Next.js%2016-black?style=flat-square&logo=next.js&logoColor=white)](frontend/)
[![Embeddings](https://img.shields.io/badge/Embeddings-FastEmbed%20ONNX-orange?style=flat-square)](https://github.com/qdrant/fastembed)
[![License](https://img.shields.io/badge/License-MIT-lightgrey?style=flat-square)](LICENSE)

🔗 **[Live Forensic Viewer](https://veridocs17.vercel.app/)** | 📦 **[GitHub Repository](https://github.com/Spidey173/Veridocs)**

---

## ⚡ At A Glance: Problem, Architecture, Proof & Scope

| Dimension | Specification |
| :--- | :--- |
| **Problem** | Traditional document bots output detached floating text without visual evidence, and fail to detect altered liability caps or SLA downgrades across multiple contract versions. |
| **Architecture** | **Pixel-level canvas coordinate grounding** mapping PDF.js text layer transform matrices (`convertToViewportRectangle`) onto canvas viewports, **sub-second hybrid retrieval** (BM25 + FAISS via FastEmbed ONNX), and an automated clause contradiction diff matrix. |
| **Evidence & Benchmarks** | Sub-second hybrid retrieval latency on CPU (~70MB RAM footprint), exact pixel coordinate alignment, backed by **107 automated unit and integration tests**. |
| **Scope & Boundaries** | **Synthetic Data**: Standard legal/financial PDFs paired with synthetic cross-version tampering benchmarks. **Local Benchmark Environment**: Sub-second hybrid retrieval and coordinate bounding boxes mapped via PDF.js viewport scaling in local Python benchmark environment. **Live UI + Local Backend**: Interactive viewer live on Vercel with client-side coordinate rendering; multi-document diffing engine runs in local container backend. |
| **Verified Test Suite** | **107 / 107 Tests passing** (FastAPI backend tests, coordinate transforms, FAISS/BM25 retrieval, contradiction diffing, Next.js build). |

---

## 🏗️ Architecture Slice: Canvas Coordinates & Contradiction Diff

```text
┌─────────────────┐       ┌────────────────────────┐       ┌────────────────────────┐       ┌─────────────────┐
│ Multi-PDF Input │ ────► │ PDF.js Transform Matrix│ ────► │ Sub-Second Hybrid RAG  │ ────► │ Contradiction   │ ────► Illuminated Visual Bounding Boxes
│ (Contract Revs) │       │ (Normalized x,y,w,h)   │       │ (BM25 + FAISS ONNX)    │       │ Clause Audit    │       (Side-by-side canvas diffs)
└─────────────────┘       └────────────────────────┘       └────────────────────────┘       └─────────────────┘
```

* **Guarantee**: Eliminates detached citations by anchoring every claim to its exact visual canvas coordinates, while immediately identifying altered terms between contract versions.

---

## 🚀 Quickstart: Reproduce in 30 Seconds

```bash
# 1. Clone repository & setup virtual environment
git clone https://github.com/Spidey173/Veridocs.git
cd Veridocs
python3 -m venv venv && source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run verified test suite (107 automated tests)
pytest backend/tests -v

# 4. Run local backend API
uvicorn backend.main:app --reload
```
*Open [http://localhost:8000](http://localhost:8000) or navigate the live interactive viewer at [veridocs17.vercel.app](https://veridocs17.vercel.app/).*

---

## 📚 Appendices & Deep Design Rationale

<details>
<summary><strong>1. Pixel-Level Coordinate Mapping via PDF.js</strong></summary>

- **Viewport Normalization**: Reads PDF text content streams, extracting glyph bounding boxes and applying `viewport.convertToViewportRectangle()` to translate raw PDF points into device-independent pixel coordinates `(x, y, width, height)`.
- **Canvas Overlay**: Injects an interactive SVG/HTML canvas layer above the rendered PDF page that draws animated highlight borders over verified source passages upon citation clicks.
</details>

<details>
<summary><strong>2. Cross-Document Contradiction Diff Engine</strong></summary>

- **Clause Alignment**: Pairs corresponding sections between Document A (e.g. Master Services Agreement) and Document B (e.g. Amendment).
- **Discrepancy Detection**: Analyzes semantic divergence, numeric token mismatches (e.g. \$1,000,000 vs \$250,000 liability cap), and omitted legal protections, rendering an actionable diff matrix.
</details>

<details>
<summary><strong>3. Project Directory Tree & Security</strong></summary>

```
Veridocs/
├── backend/
│   ├── main.py             # FastAPI endpoints & multi-tenant session isolation
│   ├── retrieval/          # Hybrid FAISS + BM25 search engine
│   ├── forensics/          # Clause contradiction diffing engine
│   └── tests/              # 107 automated tests
├── frontend/               # Next.js 16 interactive viewer & PDF.js canvas
└── requirements.txt
```
- **Anti-IDOR Security**: Session tokens are cryptographically signed with HMAC-SHA256 to isolate user documents.
- **Ephemeral Retention**: Ingested files and extracted embeddings are purged automatically after analysis.
</details>

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
