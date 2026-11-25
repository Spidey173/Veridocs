"""
SQLAlchemy 2.x database access layer for Veridocs.
Supports PostgreSQL with pgvector as primary engine, and SQLite fallback for local test runs.
"""

import json
import threading
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Generator
from contextlib import contextmanager
import numpy as np

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from config import get_settings
from models_db import (
    Base,
    Document,
    Page,
    Chunk,
    Table,
    SessionModel,
    MessageModel,
    PageVision,
    Entity,
    Extraction,
    QueryLog,
)

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None
_chunk_cache_lock = threading.Lock()
_CHUNK_CACHE_VERSION = 0


def get_chunk_cache_version() -> int:
    """Return monotonic version counter incremented whenever chunks are mutated."""
    return _CHUNK_CACHE_VERSION


def _bump_chunk_cache() -> None:
    global _CHUNK_CACHE_VERSION
    with _chunk_cache_lock:
        _CHUNK_CACHE_VERSION += 1


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = "postgresql+psycopg2://" + db_url[len("postgres://") :]
        elif db_url.startswith("postgresql://"):
            db_url = "postgresql+psycopg2://" + db_url[len("postgresql://") :]

        connect_args = {}
        if db_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False, "timeout": 15.0}
            _engine = create_engine(
                db_url,
                connect_args=connect_args,
                poolclass=StaticPool if ":memory:" in db_url else None,
            )
        else:
            _engine = create_engine(
                db_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
            )
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


def reset_engine():
    """Reset engine and session factory (useful for tests changing DATABASE_URL)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
    _bump_chunk_cache()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager yielding a transactional SQLAlchemy session."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Initialize database tables and pgvector / full-text indexes."""
    engine = get_engine()
    settings = get_settings()

    if settings.is_postgres:
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not enable pgvector extension: {e}")

    Base.metadata.create_all(bind=engine)

    if settings.DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                col_info = conn.execute(text("PRAGMA table_info(chunks)")).fetchall()
                cols = {row[1]: row[2] for row in col_info}
                if cols:
                    # Upgrade pre-existing SQLite chunks table if column types differ
                    if cols.get("id", "").upper() == "INTEGER" or "page" in cols:
                        logger.info("Upgrading SQLite 'chunks' table schema...")
                        conn.execute(text("DROP TABLE IF EXISTS chunks_backup"))
                        conn.execute(text("ALTER TABLE chunks RENAME TO chunks_backup"))
                        Chunk.__table__.create(bind=conn)
                    elif "section_path" not in cols:
                        conn.execute(text("ALTER TABLE chunks ADD COLUMN section_path VARCHAR(512)"))
                    conn.commit()
        except Exception as e:
            logger.warning(f"SQLite schema upgrade notice: {e}")

    if settings.is_postgres:
        try:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS section_path VARCHAR(512);"))
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw "
                        "ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_chunks_content_gin "
                        "ON chunks USING gin (to_tsvector('english', content));"
                    )
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"PostgreSQL index creation notice: {e}")

    logger.info("Veridocs database schema initialized successfully.")


# ----------------------------------------------------------------------
# Session and Chunk Operations
# ----------------------------------------------------------------------


def save_session(session_id: str, file_names: List[str], suggested_questions: Optional[List[str]] = None):
    """Insert or update session with file names and suggested questions."""
    with get_db() as db:
        sess = db.get(SessionModel, session_id)
        if sess:
            current_files = sess.file_names or []
            merged = list(dict.fromkeys(current_files + file_names))
            sess.file_names = merged
            if suggested_questions is not None:
                sess.suggested_questions = suggested_questions
        else:
            sess = SessionModel(
                session_id=session_id,
                created_at=time.time(),
                file_names=file_names,
                suggested_questions=suggested_questions or [],
            )
            db.add(sess)

    try:
        cleanup_expired_sessions(max_sessions=20)
    except Exception:
        pass


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve session metadata, chunk count, and suggestions."""
    with get_db() as db:
        sess = db.get(SessionModel, session_id)
        if not sess:
            return None

        chunk_count = db.query(Chunk).filter(Chunk.session_id == session_id).count()
        return {
            "session_id": sess.session_id,
            "created_at": sess.created_at,
            "file_names": sess.file_names or [],
            "chunk_count": chunk_count,
            "suggested_questions": sess.suggested_questions or [],
        }


def save_chunks(
    session_id: str, chunks: List[Dict[str, Any]], embeddings: List[np.ndarray], document_id: Optional[str] = None
):
    """Persist chunks and embeddings for a session and/or document."""
    chunk_models: List[Chunk] = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        emb_arr = np.asarray(emb, dtype=np.float32)
        norm = np.linalg.norm(emb_arr)
        if norm > 0:
            emb_arr = emb_arr / norm

        filename = chunk.get("source_file") or chunk.get("filename") or "document"
        page_num = chunk.get("page") or chunk.get("page_number") or 1
        content = chunk.get("text") or chunk.get("content") or ""
        chunk_type = chunk.get("chunk_type") or "text"
        meta = dict(
            chunk.get("metadata")
            or {
                "source_file": filename,
                "page": page_num,
                "chunk_type": chunk_type,
                "extraction_method": chunk.get("extraction_method", "text_layer"),
                "ocr_confidence": chunk.get("ocr_confidence"),
            }
        )
        section_path = chunk.get("section_path") or meta.get("section_path")
        if section_path and "section_path" not in meta:
            meta["section_path"] = section_path

        emb_value = emb_arr.tolist()

        chunk_models.append(
            Chunk(
                document_id=document_id or chunk.get("document_id"),
                session_id=session_id,
                filename=filename,
                page_number=page_num,
                chunk_index=i,
                content=content,
                chunk_type=chunk_type,
                section_path=section_path,
                embedding=emb_value,
                metadata_json=meta,
            )
        )
    if chunk_models:
        with get_db() as db:
            db.add_all(chunk_models)
        _bump_chunk_cache()


def get_chunks_and_embeddings(
    session_id: Optional[str] = None, active_files: Optional[List[str]] = None
) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """Retrieve stored chunks (scoped to a session or across the library) and embedding matrix."""
    with get_db() as db:
        q = db.query(Chunk)
        if session_id:
            q = q.filter(Chunk.session_id == session_id)
        if active_files:
            q = q.filter(Chunk.filename.in_(active_files))
        rows = q.order_by(Chunk.chunk_index.asc()).all()

        if not rows:
            return [], np.empty((0, 0), dtype=np.float32)

        chunks = []
        emb_list = []
        for r in rows:
            meta = r.metadata_json or {}
            chunks.append(
                {
                    "id": r.id,
                    "document_id": r.document_id,
                    "session_id": r.session_id,
                    "source_file": r.filename,
                    "filename": r.filename,
                    "page": r.page_number,
                    "text": r.content,
                    "chunk_type": r.chunk_type,
                    "section_path": r.section_path or meta.get("section_path"),
                    "metadata": meta,
                }
            )

            if r.embedding is not None:
                if isinstance(r.embedding, (bytes, bytearray)):
                    emb = np.frombuffer(r.embedding, dtype=np.float32)
                elif isinstance(r.embedding, (list, tuple, np.ndarray)):
                    emb = np.asarray(r.embedding, dtype=np.float32)
                elif isinstance(r.embedding, str):
                    try:
                        emb = np.asarray(json.loads(r.embedding), dtype=np.float32)
                    except Exception:
                        # Vector string representation like "[0.1, 0.2, ...]"
                        cleaned = r.embedding.strip("[] \t\n")
                        emb = np.fromstring(cleaned, sep=",", dtype=np.float32)
                else:
                    emb = np.asarray(r.embedding, dtype=np.float32)
                emb_list.append(emb)

        if emb_list:
            emb_matrix = np.vstack(emb_list)
        else:
            emb_matrix = np.empty((0, 0), dtype=np.float32)

        return chunks, emb_matrix


def delete_session(session_id: str) -> bool:
    """Delete session, associated chunks, documents, and messages."""
    with get_db() as db:
        db.query(Chunk).filter(Chunk.session_id == session_id).delete(synchronize_session=False)
        db.query(Document).filter(Document.session_id == session_id).delete(synchronize_session=False)
        db.query(MessageModel).filter(MessageModel.session_id == session_id).delete(synchronize_session=False)
        count = db.query(SessionModel).filter(SessionModel.session_id == session_id).delete(synchronize_session=False)
    _bump_chunk_cache()
    return count > 0


def delete_document(session_id: str, document_name: str) -> bool:
    """Delete a single document's chunks and remove it from the session."""
    with get_db() as db:
        db.query(Chunk).filter(Chunk.session_id == session_id, Chunk.filename == document_name).delete(
            synchronize_session=False
        )
        db.query(Document).filter(Document.session_id == session_id, Document.filename == document_name).delete(
            synchronize_session=False
        )
        sess = db.get(SessionModel, session_id)
        if sess and sess.file_names:
            sess.file_names = [f for f in sess.file_names if f != document_name]
    _bump_chunk_cache()
    return True


def list_sessions() -> List[Dict[str, Any]]:
    """List all sessions with their chunk counts in a single grouped query."""
    with get_db() as db:
        sessions = db.query(SessionModel).order_by(SessionModel.created_at.desc()).all()
        counts = dict(db.query(Chunk.session_id, func.count(Chunk.id)).group_by(Chunk.session_id).all())
        return [
            {
                "session_id": s.session_id,
                "created_at": s.created_at,
                "file_names": s.file_names or [],
                "chunk_count": int(counts.get(s.session_id, 0)),
            }
            for s in sessions
        ]


def cleanup_expired_sessions(max_age_seconds: float = 86400, max_sessions: int = 20) -> int:
    """Prune expired or excess non-demo sessions."""
    settings = get_settings()
    now = time.time()
    cutoff = now - max_age_seconds
    deleted_count = 0

    with get_db() as db:
        expired = (
            db.query(SessionModel)
            .filter(SessionModel.session_id != "demo-session", SessionModel.created_at < cutoff)
            .all()
        )

        total = db.query(SessionModel).filter(SessionModel.session_id != "demo-session").count()
        excess = []
        if total > max_sessions:
            limit = total - max_sessions
            excess = (
                db.query(SessionModel)
                .filter(SessionModel.session_id != "demo-session")
                .order_by(SessionModel.created_at.asc())
                .limit(limit)
                .all()
            )

        to_remove = {s.session_id: s.file_names for s in (expired + excess)}

        for sid, fnames in to_remove.items():
            db.query(Chunk).filter(Chunk.session_id == sid).delete(synchronize_session=False)
            db.query(Document).filter(Document.session_id == sid).delete(synchronize_session=False)
            db.query(SessionModel).filter(SessionModel.session_id == sid).delete(synchronize_session=False)
            deleted_count += 1

            if fnames:
                for f in fnames:
                    fp = settings.UPLOAD_DIR / f"{sid}_{f}"
                    if fp.exists():
                        fp.unlink(missing_ok=True)

    return deleted_count


# ----------------------------------------------------------------------
# Document Entity Helpers
# ----------------------------------------------------------------------


def create_document(
    filename: str,
    mime_type: str,
    session_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    status: str = "queued",
) -> Dict[str, Any]:
    """Create a new Document record with status='queued'."""
    with get_db() as db:
        doc = Document(
            filename=filename,
            mime_type=mime_type,
            session_id=session_id,
            doc_type=doc_type,
            status=status,
            created_at=time.time(),
            updated_at=time.time(),
        )
        db.add(doc)
        db.flush()
        return doc.to_dict()


def get_document(document_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve document by ID."""
    with get_db() as db:
        doc = db.get(Document, document_id)
        return doc.to_dict() if doc else None


def update_document_status(
    document_id: str, status: str, error: Optional[str] = None, page_count: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Update document processing stage status and error message."""
    with get_db() as db:
        doc = db.get(Document, document_id)
        if not doc:
            return None
        doc.status = status
        doc.updated_at = time.time()
        if error is not None:
            doc.error = error
        if page_count is not None:
            doc.page_count = page_count
        db.flush()
        return doc.to_dict()


def save_document_pages(document_id: str, pages: List[Dict[str, Any]]):
    """Save parsed page records for a document."""
    with get_db() as db:
        for p in pages:
            page_record = Page(
                document_id=document_id,
                page_number=p["page_number"],
                text=p.get("text", ""),
                extraction_method=p.get("extraction_method", "text_layer"),
                ocr_confidence=p.get("ocr_confidence"),
                has_figures=p.get("has_figures", False),
                has_tables=p.get("has_tables", False),
                has_signature_block=p.get("has_signature_block", False),
            )
            db.add(page_record)


def save_document_tables(document_id: str, tables: List[Dict[str, Any]]):
    """Save extracted table markdown and JSON structures for a document."""
    with get_db() as db:
        for t in tables:
            tbl = Table(
                document_id=document_id,
                page_number=t.get("page_number", 1),
                markdown=t.get("markdown", ""),
                table_json=t.get("json", {}),
                bbox=t.get("bbox"),
            )
            db.add(tbl)


def get_document_tables(document_id: str) -> List[Dict[str, Any]]:
    """Retrieve all extracted tables for a document."""
    with get_db() as db:
        tbls = db.query(Table).filter(Table.document_id == document_id).order_by(Table.page_number.asc()).all()
        return [t.to_dict() for t in tbls]


def get_document_pages(document_id: str) -> List[Dict[str, Any]]:
    """Retrieve all pages for a document."""
    with get_db() as db:
        pages = db.query(Page).filter(Page.document_id == document_id).order_by(Page.page_number.asc()).all()
        return [p.to_dict() for p in pages]


# ----------------------------------------------------------------------
# Vision Persistence
# ----------------------------------------------------------------------


def save_page_vision(
    document_id: str,
    page_number: int,
    json_data: Dict[str, Any],
    model: str,
    image_hash: Optional[str] = None,
    cost_tokens: int = 0,
) -> Dict[str, Any]:
    """Persist multimodal vision analysis output for a page."""
    with get_db() as db:
        pv = PageVision(
            document_id=document_id,
            page_number=page_number,
            image_hash=image_hash,
            json_data=json_data,
            model=model,
            cost_tokens=cost_tokens,
            created_at=time.time(),
        )
        db.add(pv)
        db.flush()
        return pv.to_dict()


def get_page_vision(document_id: str) -> List[Dict[str, Any]]:
    """Retrieve all vision analyses for a document."""
    with get_db() as db:
        results = (
            db.query(PageVision)
            .filter(PageVision.document_id == document_id)
            .order_by(PageVision.page_number.asc())
            .all()
        )
        return [r.to_dict() for r in results]


def get_cached_page_vision_by_hash(image_hash: str) -> Optional[Dict[str, Any]]:
    """Lookup cached vision output by image hash to avoid duplicate LLM vision calls."""
    if not image_hash:
        return None
    with get_db() as db:
        cached = db.query(PageVision).filter(PageVision.image_hash == image_hash).first()
        return cached.to_dict() if cached else None


# ----------------------------------------------------------------------
# Classification, Entities, and Structured Extractions
# ----------------------------------------------------------------------


def update_document_classification(
    document_id: str, doc_type: str, confidence: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """Update document classification (doc_type and confidence)."""
    with get_db() as db:
        doc = db.get(Document, document_id)
        if not doc:
            return None
        doc.doc_type = doc_type
        if confidence is not None:
            doc.doc_type_confidence = confidence
        doc.updated_at = time.time()
        db.flush()
        return doc.to_dict()


def save_entities(document_id: str, entities_list: List[Dict[str, Any]]):
    """Save normalized named entities extracted from document chunks."""
    with get_db() as db:
        for ent in entities_list:
            e = Entity(
                document_id=document_id,
                page_number=ent.get("page_number") or ent.get("page", 1),
                chunk_id=ent.get("chunk_id"),
                label=ent.get("label", "other"),
                text=ent.get("text", ""),
                normalized=ent.get("normalized"),
                start_offset=ent.get("start_offset"),
                end_offset=ent.get("end_offset"),
                score=ent.get("score", 1.0),
                created_at=time.time(),
            )
            db.add(e)


def get_entities(document_id: str, label: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve extracted entities for a document, optionally filtered by label."""
    with get_db() as db:
        q = db.query(Entity).filter(Entity.document_id == document_id)
        if label:
            q = q.filter(Entity.label == label.lower())
        results = q.order_by(Entity.page_number.asc(), Entity.created_at.asc()).all()
        return [e.to_dict() for e in results]


def save_extraction(
    document_id: str,
    schema_type: str,
    json_data: Dict[str, Any],
    verified_ratio: float = 0.0,
    user_edits: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist structured schema extraction results with field evidence and verified ratio."""
    with get_db() as db:
        ext = db.query(Extraction).filter(Extraction.document_id == document_id).first()
        if not ext:
            ext = Extraction(
                document_id=document_id,
                schema_type=schema_type,
                json_data=json_data,
                verified_ratio=verified_ratio,
                user_edits=user_edits or {},
                created_at=time.time(),
                updated_at=time.time(),
            )
            db.add(ext)
        else:
            ext.schema_type = schema_type
            ext.json_data = json_data
            ext.verified_ratio = verified_ratio
            if user_edits is not None:
                ext.user_edits = user_edits
            ext.updated_at = time.time()
        db.flush()
        return ext.to_dict()


def get_extraction(document_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve structured schema extraction for a document."""
    with get_db() as db:
        ext = db.query(Extraction).filter(Extraction.document_id == document_id).first()
        return ext.to_dict() if ext else None


def update_extraction_user_edits(document_id: str, user_edits: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Save manual user edits on extracted fields without overwriting model output."""
    with get_db() as db:
        ext = db.query(Extraction).filter(Extraction.document_id == document_id).first()
        if not ext:
            return None
        current_edits = dict(ext.user_edits or {})
        current_edits.update(user_edits)
        ext.user_edits = current_edits
        ext.updated_at = time.time()
        db.flush()
        return ext.to_dict()


def log_query(
    session_id: Optional[str],
    question: str,
    retrieval_strategy: Optional[str] = "hybrid",
    citation_score: Optional[float] = None,
    total_claims: int = 0,
    supported_claims: int = 0,
) -> Dict[str, Any]:
    """Persist a query execution entry to query_log for analytics."""
    with get_db() as db:
        entry = QueryLog(
            session_id=session_id,
            question=question,
            retrieval_strategy=retrieval_strategy,
            citation_score=citation_score,
            total_claims=total_claims,
            supported_claims=supported_claims,
            created_at=time.time(),
        )
        db.add(entry)
        db.flush()
        return entry.to_dict()
