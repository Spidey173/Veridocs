"""
Pytest configuration and shared fixtures for Veridocs.
"""

import sys
import os
import io
import shutil
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import numpy as np
from fastapi.testclient import TestClient
from pypdf import PdfWriter
import docx

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import main
from config import get_settings, ModelRegistry, get_model_registry
from conversation import get_conversation_manager
from models import (
    DocumentInsights,
    ExecutiveSummary,
    EntityInfo,
    CitationInfo,
)


@pytest.fixture(autouse=True)
def clean_environment(tmp_path, monkeypatch):
    """
    Ensure clean state for every test:
    - Dedicated temp upload directory
    - In-memory sessions dictionary reset
    - Conversation manager cleared
    """
    test_upload_dir = tmp_path / "test_uploads"
    test_upload_dir.mkdir(parents=True, exist_ok=True)
    
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(test_upload_dir))
    
    # Clear active sessions in main
    main.sessions.clear()
    
    # Clear conversation manager
    cm = get_conversation_manager()
    cm._conversations.clear()
    
    yield
    
    # Teardown
    main.sessions.clear()
    cm._conversations.clear()
    if test_upload_dir.exists():
        shutil.rmtree(test_upload_dir, ignore_errors=True)


@pytest.fixture
def mock_embedding_model():
    """Mock SentenceTransformer embedding model producing deterministic vectors."""
    mock = MagicMock()
    
    def mock_encode(texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        # Generate predictable 384-dimensional unit vectors
        vectors = []
        for i, text in enumerate(texts):
            # Seed based on length and first char for semi-consistency
            seed = sum(ord(c) for c in text[:10]) % 1000
            np.random.seed(seed)
            vec = np.random.randn(384).astype(np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.array(vectors, dtype=np.float32)
    
    mock.encode.side_effect = mock_encode
    return mock


@pytest.fixture
def mock_reranker_model():
    """Mock CrossEncoder reranker model producing predictable scores."""
    mock = MagicMock()
    
    def mock_predict(pairs, **kwargs):
        scores = []
        for query, text in pairs:
            # Simple keyword overlap heuristic for test ranking
            q_words = set(query.lower().split())
            t_words = set(text.lower().split())
            overlap = len(q_words & t_words)
            scores.append(float(overlap) + 0.1)
        return np.array(scores, dtype=np.float32)
    
    mock.predict.side_effect = mock_predict
    return mock


@pytest.fixture
def patch_models(mock_embedding_model, mock_reranker_model, monkeypatch):
    """Patch the singleton ModelRegistry with our mock models."""
    registry = get_model_registry()
    monkeypatch.setattr(registry, "_embedding_model", mock_embedding_model)
    monkeypatch.setattr(registry, "_reranker_model", mock_reranker_model)
    return registry


@pytest.fixture
def sample_txt_bytes():
    """Sample text document bytes."""
    content = (
        "1. Executive Overview\n"
        "Veridocs is an enterprise-grade document intelligence platform.\n"
        "It supports PDF, DOCX, and TXT files with high retrieval precision.\n\n"
        "2. Financial Performance\n"
        "The project raised $2.5 million in revenue during Q3 2024.\n"
        "Operating profit increased by 35% compared to FY2023.\n"
        "CEO Jane Doe announced strategic partnerships in New York and London.\n"
    )
    return content.encode("utf-8")


@pytest.fixture
def sample_pdf_bytes():
    """Generate a minimal valid PDF with extractable text."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def sample_docx_bytes():
    """Generate a valid in-memory DOCX document."""
    doc = docx.Document()
    doc.add_heading("Project Overview", level=1)
    doc.add_paragraph("Veridocs extracts key insights and answers user questions with citations.")
    doc.add_paragraph("Dr. Alan Turing confirmed 50% performance efficiency in San Francisco.")
    
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def sample_chunks():
    """Sample chunked documents for vector search & reranker tests."""
    return [
        {
            "text": "Veridocs provides two-stage retrieval using FAISS and Cross-Encoder.",
            "page": 1,
            "source_file": "doc1.pdf",
            "section": "Architecture",
        },
        {
            "text": "The platform includes automated claim-level grounding verification.",
            "page": 2,
            "source_file": "doc1.pdf",
            "section": "Verification",
        },
        {
            "text": "Q3 2024 revenue reached $2.5 million representing a 35% increase.",
            "page": 1,
            "source_file": "financials.pdf",
            "section": "Finance",
        },
    ]


@pytest.fixture
def mock_llm_service(monkeypatch):
    """Mock FreeLLMService to prevent external API calls and provide deterministic outputs."""
    from llm_service import FreeLLMService

    def mock_generate_answer(self, question, chunks, history=None):
        return f"Based on the provided context [Page 1], Veridocs uses FAISS and Cross-Encoder."

    def mock_generate_summary(self, content):
        return {
            "purpose": "A test document describing Veridocs.",
            "key_findings": ["Two-stage retrieval", "Claim grounding"],
            "risks": ["Model availability"],
            "conclusions": ["Production ready"],
        }

    def mock_generate_questions(self, content):
        return [
            "What retrieval models are used?",
            "What was the Q3 2024 revenue?",
            "How does grounding verification work?",
        ]

    def mock_generate_summary_and_questions(self, chunks):
        return {
            "purpose": "A test document describing Veridocs.",
            "key_findings": ["Two-stage retrieval", "Claim grounding"],
            "risks": ["Model availability"],
            "conclusions": ["Production ready"],
        }, [
            "What retrieval models are used?",
            "What was the Q3 2024 revenue?",
            "How does grounding verification work?",
        ]

    async def mock_generate_answer_stream(self, question, chunks, history=None):
        tokens = ["Based ", "on ", "page ", "1", ", Veridocs ", "works."]
        for token in tokens:
            yield token

    def mock_init(self, provider=None, model=None):
        self.provider = "mock"
        self.model = "mock-model"
        self.settings = get_settings()
        self.client = MagicMock()

    monkeypatch.setattr(FreeLLMService, "__init__", mock_init)
    monkeypatch.setattr(FreeLLMService, "generate_answer", mock_generate_answer)
    monkeypatch.setattr(FreeLLMService, "generate_summary", mock_generate_summary)
    monkeypatch.setattr(FreeLLMService, "generate_suggested_questions", mock_generate_questions)
    monkeypatch.setattr(FreeLLMService, "generate_summary_and_questions", mock_generate_summary_and_questions)
    monkeypatch.setattr(FreeLLMService, "generate_answer_stream", mock_generate_answer_stream)


@pytest.fixture
def test_client(patch_models, mock_llm_service):
    """FastAPI TestClient with patched models and mocked LLM services."""
    client = TestClient(main.app)
    return client
