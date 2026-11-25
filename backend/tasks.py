"""
Background task processing pipeline for Veridocs documents:
queued -> parsing -> ocr -> chunking -> embedding -> ready | failed.
Handles retries, per-stage error persistence, and live SSE event broadcasting.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from config import get_settings, get_model_registry
import database
from queue_service import publish_status_event
from ingestion.router import parse_document
from pdf_processor import chunk_text
from vision.classifier import classify_page_heuristics
from vision.service import VisionService
from classification.classifier import classify_document
from entities.extractor import EntityExtractor
from extraction.extractor import SchemaExtractor

logger = logging.getLogger(__name__)


def process_document_pipeline(document_id: str, file_path_str: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute end-to-end ingestion pipeline:
    1. parsing: layout and digital text extraction
    2. ocr: per-page text density check and OCR fallback
    3. chunking: ~600 chars passage chunking + dedicated table chunks
    4. embedding: 384-dim Fastembed vector generation
    5. ready: persistence and session indexing
    """
    settings = get_settings()
    file_path = Path(file_path_str)
    filename = file_path.name
    sid = session_id or "default"

    def transition(status: str, stage_msg: str, **kwargs):
        logger.info(f"[Pipeline] Doc {document_id} ({filename}) -> {status}: {stage_msg}")
        database.update_document_status(document_id, status=status)
        publish_status_event(
            document_id,
            {
                "document_id": document_id,
                "session_id": sid,
                "filename": filename,
                "status": status,
                "stage_message": stage_msg,
                **kwargs,
            },
        )

    try:
        # Stage 1: Parsing
        transition("parsing", "Extracting document structure and text layer")
        parsed = parse_document(file_path, filename=filename)

        database.update_document_status(document_id, status="parsing", page_count=parsed.total_pages)

        # Stage 2: OCR & Tables
        transition("ocr", f"Verifying OCR quality across {parsed.total_pages} pages")
        pages_data: List[Dict[str, Any]] = []
        tables_data: List[Dict[str, Any]] = []

        for p in parsed.pages:
            flags = classify_page_heuristics(p.text, page_number=p.number, tables=p.tables)
            has_fig = p.has_figures or flags["has_figures"]
            has_tbl = p.has_tables or flags["has_tables"]
            has_sig = flags["has_signature_block"]

            p_dict = {
                "page": p.number,
                "page_number": p.number,
                "text": p.text,
                "blocks": p.blocks,
                "extraction_method": p.extraction_method,
                "ocr_confidence": p.ocr_confidence,
                "has_figures": has_fig,
                "has_tables": has_tbl,
                "has_signature_block": has_sig,
                "tables": [t.model_dump() for t in p.tables],
            }
            pages_data.append(p_dict)

            for t in p.tables:
                tables_data.append(
                    {
                        "page_number": t.page_number,
                        "markdown": t.markdown,
                        "json": t.json_data,
                        "bbox": t.bbox,
                    }
                )

        database.save_document_pages(document_id, pages_data)
        if tables_data:
            database.save_document_tables(document_id, tables_data)

        # Stage 3: Chunking
        transition("chunking", "Generating cohesive passage and table chunks")
        chunks = chunk_text(
            pages_data,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            document_name=filename,
            document_id=document_id,
        )

        if not chunks:
            raise ValueError("Document yielded no text or table chunks to index.")

        # Stage 4: Vision Analysis (flagged pages only, budget-capped, non-blocking)
        transition("vision", "Analyzing visual figures and signature blocks on flagged pages")
        vision_outputs = []
        try:
            vision_service = VisionService()
            vision_res = vision_service.process_document_vision(document_id, pages_data, file_path)
            fig_chunks = vision_res.get("figure_chunks", [])
            if fig_chunks:
                for idx, fc in enumerate(fig_chunks):
                    fc["source_file"] = filename
                    fc["chunk_index"] = len(chunks) + idx
                chunks.extend(fig_chunks)
                logger.info(f"Integrated {len(fig_chunks)} figure chunks into retrieval index")

            vision_outputs = database.get_page_vision(document_id)

            if vision_res.get("warning"):
                publish_status_event(
                    document_id,
                    {
                        "document_id": document_id,
                        "session_id": sid,
                        "status": "vision",
                        "stage_message": f"Vision stage completed with warning: {vision_res['warning']}",
                        "warning": vision_res["warning"],
                    },
                )
        except Exception as e:
            logger.warning(f"Vision stage skipped for doc {document_id}: {e}")
            publish_status_event(
                document_id,
                {
                    "document_id": document_id,
                    "session_id": sid,
                    "status": "vision",
                    "stage_message": f"Vision stage skipped: {str(e)}",
                    "warning": str(e),
                },
            )

        # Stage 5: Classification, Entities, and Structured Extraction
        transition("extraction", "Extracting document type, named entities, and verified structured schema")
        doc_type, doc_conf = "other", 0.6
        try:
            doc_type, doc_conf = classify_document(pages_data, filename=filename)
            database.update_document_classification(document_id, doc_type=doc_type, confidence=doc_conf)

            # Entity extraction
            if settings.NER_ENABLED:
                extractor = EntityExtractor()
                entities = extractor.extract_and_dedupe_document(document_id, chunks)
                if entities:
                    database.save_entities(document_id, entities)
                    logger.info(f"Saved {len(entities)} extracted entities for doc {document_id}")

            # Structured schema extraction
            if settings.EXTRACTION_ENABLED:
                schema_extractor = SchemaExtractor()
                ext_res = schema_extractor.extract(
                    document_id=document_id,
                    doc_type=doc_type,
                    pages=pages_data,
                    tables=tables_data,
                    vision_outputs=vision_outputs,
                )
                database.save_extraction(
                    document_id=document_id,
                    schema_type=doc_type,
                    json_data=ext_res["fields"],
                    verified_ratio=ext_res["verified_ratio"],
                )
                logger.info(
                    f"Structured extraction completed for doc {document_id} ({doc_type}, verified ratio: {ext_res['verified_ratio']})"
                )

            # Anomaly and risk flags (heuristic signals for human review)
            if settings.FLAGS_ENABLED:
                try:
                    with database.get_db() as db:
                        from flags.checker import FlagCheckerService

                        flag_service = FlagCheckerService(db)
                        flag_service.run_all_checks(document_id, pdf_metadata=parsed.metadata)
                        logger.info(f"Anomaly flag analysis completed for doc {document_id}")
                except Exception as ef:
                    logger.warning(f"Anomaly flag checking failed for {document_id}: {ef}")

            # Knowledge graph construction
            try:
                with database.get_db() as db:
                    from graph.builder import KnowledgeGraphBuilder

                    graph_builder = KnowledgeGraphBuilder(db)
                    graph_builder.build_for_document(document_id)
                    logger.info(f"Knowledge graph constructed for doc {document_id}")
            except Exception as eg:
                logger.warning(f"Knowledge graph construction failed for {document_id}: {eg}")
        except Exception as e:
            logger.warning(f"Classification and extraction stage skipped for {document_id}: {e}")

        # Stage 6: Embedding
        transition("embedding", f"Computing dense vector embeddings for {len(chunks)} chunks")
        reg = get_model_registry()
        chunk_texts = [c["text"] for c in chunks]
        embeddings = list(reg.embedding_model.embed(chunk_texts, batch_size=32))

        # Save to database
        database.save_chunks(sid, chunks, embeddings, document_id=document_id)

        # Update session metadata if session_id provided
        if session_id:
            database.save_session(session_id, [filename])

        # Stage 6: Ready
        transition(
            "ready",
            f"Successfully indexed {len(chunks)} chunks across {parsed.total_pages} pages",
            chunk_count=len(chunks),
            page_count=parsed.total_pages,
            table_count=len(tables_data),
        )

        return {
            "status": "ready",
            "document_id": document_id,
            "session_id": sid,
            "chunk_count": len(chunks),
            "page_count": parsed.total_pages,
            "table_count": len(tables_data),
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Pipeline Failed] Doc {document_id}: {error_msg}", exc_info=True)
        database.update_document_status(document_id, status="failed", error=error_msg)
        publish_status_event(
            document_id,
            {
                "document_id": document_id,
                "session_id": sid,
                "filename": filename,
                "status": "failed",
                "error": error_msg,
                "stage_message": f"Processing failed: {error_msg}",
            },
        )
        return {
            "status": "failed",
            "document_id": document_id,
            "error": error_msg,
        }


def process_comparison_task(comparison_id: str, doc_a_id: str, doc_b_id: str) -> Dict[str, Any]:
    """
    Background worker task for pairwise contract comparison.
    Broadcasts live progress via Redis SSE and updates database.
    """
    from comparison.service import ComparisonService

    def transition(status: str, stage_msg: str, **kwargs):
        publish_status_event(
            comparison_id,
            {
                "comparison_id": comparison_id,
                "doc_a": doc_a_id,
                "doc_b": doc_b_id,
                "status": status,
                "stage_message": stage_msg,
                **kwargs,
            },
        )

    transition("processing", "Segmenting contract clauses and aligning sections")
    try:
        with database.get_db() as db:
            service = ComparisonService(db)
            service.run_comparison(doc_a_id, doc_b_id, comparison_id=comparison_id)

        transition(
            "ready",
            "Comparison completed successfully",
            status="ready",
        )
        return {
            "status": "ready",
            "comparison_id": comparison_id,
        }
    except Exception as e:
        logger.exception(f"Comparison task failed: {e}")
        transition("failed", f"Comparison failed: {e}", error=str(e))
        return {
            "status": "failed",
            "comparison_id": comparison_id,
            "error": str(e),
        }


def process_summary_task(document_id: str) -> Dict[str, Any]:
    """Background worker task for map-reduce document summarization + NLI verification."""
    from summarizer import DocumentSummarizer

    publish_status_event(
        document_id,
        {
            "document_id": document_id,
            "status": "processing",
            "stage_message": "Generating structured map-reduce summary",
        },
    )
    try:
        with database.get_db() as db:
            summarizer = DocumentSummarizer(db)
            record = summarizer.generate_and_save(document_id)
            res = record.to_dict()

        publish_status_event(
            document_id,
            {
                "document_id": document_id,
                "status": "ready",
                "grounding_score": res.get("grounding_score"),
                "stage_message": "Summary completed",
            },
        )
        return {
            "status": "ready",
            "document_id": document_id,
            "grounding_score": res.get("grounding_score"),
        }
    except Exception as e:
        logger.exception(f"Summary task failed for {document_id}: {e}")
        publish_status_event(
            document_id,
            {
                "document_id": document_id,
                "status": "failed",
                "error": str(e),
            },
        )
        return {
            "status": "failed",
            "document_id": document_id,
            "error": str(e),
        }
