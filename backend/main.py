"""
Veridocs — Document Intelligence & Verification Engine API.
Lightweight, fast, and real: local Fastembed ONNX embeddings, SQLite persistence,
OpenAI-compatible streaming QA, and honest citation checks.
"""

import sys
import shutil
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend directory is in sys.path so un-prefixed imports work
# regardless of invocation directory or entrypoint format
_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from config import get_settings, get_model_registry
import database
from pdf_processor import extract_text_from_file, chunk_text
from routers import documents, query, system

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("veridocs")


def seed_demo_session_if_needed():
    """Ensure sample_agreement.pdf is indexed into SQLite for instant showcase."""
    try:
        session = database.get_session("demo-session")
        if session and session["chunk_count"] > 0:
            if not session.get("suggested_questions"):
                database.save_session(
                    "demo-session",
                    session["file_names"],
                    suggested_questions=[
                        "What are the payment terms in this agreement?",
                        "What is the limitation of liability and uptime SLA?",
                        "What data protection and encryption standards are required?",
                    ],
                )
            return

        settings = get_settings()
        sample_path = Path(__file__).resolve().parent / "public" / "sample_agreement.pdf"
        if not sample_path.exists():
            sample_path = Path(__file__).resolve().parent.parent / "public" / "sample_agreement.pdf"
        if not sample_path.exists():
            sample_path = settings.UPLOAD_DIR / "sample_agreement.pdf"

        if sample_path.exists():
            logger.info("Indexing sample_agreement.pdf into demo-session...")
            pages = extract_text_from_file(sample_path, filename="sample_agreement.pdf")
            chunks = chunk_text(pages, chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP, document_name="sample_agreement.pdf")

            reg = get_model_registry()
            chunk_texts = [c["text"] for c in chunks]
            embeddings = list(reg.embedding_model.embed(chunk_texts))

            database.save_session(
                "demo-session",
                ["sample_agreement.pdf"],
                suggested_questions=[
                    "What are the payment terms in this agreement?",
                    "What is the limitation of liability and uptime SLA?",
                    "What data protection and encryption standards are required?",
                ],
            )
            database.save_chunks("demo-session", chunks, embeddings)

            dest = settings.UPLOAD_DIR / "demo-session_sample_agreement.pdf"
            if not dest.exists():
                shutil.copyfile(sample_path, dest)
            logger.info("Demo session seeded successfully.")
    except Exception as e:
        logger.warning(f"Could not seed demo session: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize SQLite database schema and seed demo document on startup."""
    logger.info("Initializing Veridocs SQLite database...")
    database.init_db()
    database.cleanup_expired_sessions()
    seed_demo_session_if_needed()
    logger.info("Veridocs backend ready.")
    yield


settings = get_settings()

app = FastAPI(
    title="Veridocs API",
    version="0.2.0",
    description="Document Question Answering with real citations and grounding verification",
    lifespan=lifespan,
)

# CORS middleware
origins = settings.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount core routers
app.include_router(system.router)
app.include_router(documents.router)
app.include_router(query.router)


@app.get("/")
async def root():
    return {
        "name": "Veridocs API",
        "version": "0.2.0",
        "status": "online",
        "docs_url": "/docs",
    }
