"""
Contract comparison routes for Veridocs.
Endpoints:
- POST /comparisons: Enqueues background pairwise contract comparison
- GET /comparisons/{id}: Returns comparison status, redlines, and risk summary
- GET /comparisons/{id}/events: SSE stream for live comparison progress
- GET /comparisons/{id}/export: Exports comparison redline and risk report to Markdown
"""

import json
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import StreamingResponse

import database
from models_db import Document, Comparison
from queue_service import enqueue_task, subscribe_status_events
from tasks import process_comparison_task
from comparison.service import export_comparison_to_markdown

logger = logging.getLogger(__name__)
router = APIRouter(tags=["comparisons"])


@router.post("/comparisons")
@router.post("/api/comparisons")
async def create_comparison(request: Request, payload: Dict[str, Any] = Body(...)):
    """
    POST /comparisons: Creates a new comparison job between doc_a and doc_b,
    enqueues the background analysis task, and returns immediately with the job id.
    """
    doc_a_id = payload.get("doc_a")
    doc_b_id = payload.get("doc_b")

    if not doc_a_id or not doc_b_id:
        raise HTTPException(status_code=400, detail="Both 'doc_a' and 'doc_b' document IDs are required.")

    with database.get_db() as db:
        doc_a = db.query(Document).filter(Document.id == doc_a_id).first()
        doc_b = db.query(Document).filter(Document.id == doc_b_id).first()

        if not doc_a:
            raise HTTPException(status_code=404, detail=f"Document A '{doc_a_id}' not found.")
        if not doc_b:
            raise HTTPException(status_code=404, detail=f"Document B '{doc_b_id}' not found.")

        comp = Comparison(doc_a=doc_a_id, doc_b=doc_b_id, status="queued")
        db.add(comp)
        db.commit()
        db.refresh(comp)
        comp_id = comp.id

    # Enqueue comparison job for background processing
    enqueue_task(process_comparison_task, comp_id, doc_a_id, doc_b_id)

    return {
        "id": comp_id,
        "doc_a": doc_a_id,
        "doc_b": doc_b_id,
        "status": "queued",
        "stage_message": "Comparison job queued for processing",
    }


@router.get("/comparisons/{comparison_id}")
@router.get("/api/comparisons/{comparison_id}")
async def get_comparison_status(comparison_id: str):
    """
    GET /comparisons/{id}: Returns current status and full diff analysis payload.
    """
    with database.get_db() as db:
        comp = db.query(Comparison).filter(Comparison.id == comparison_id).first()
        if not comp:
            raise HTTPException(status_code=404, detail=f"Comparison '{comparison_id}' not found.")
        return comp.to_dict()


@router.get("/comparisons/{comparison_id}/events")
@router.get("/api/comparisons/{comparison_id}/events")
async def get_comparison_events(comparison_id: str):
    """
    GET /comparisons/{id}/events: Server-Sent Events (SSE) live stream
    of comparison pipeline stage transitions.
    """
    with database.get_db() as db:
        comp = db.query(Comparison).filter(Comparison.id == comparison_id).first()
        if not comp:
            raise HTTPException(status_code=404, detail=f"Comparison '{comparison_id}' not found.")

    async def event_generator():
        yield f"data: {json.dumps({'comparison_id': comparison_id, 'status': comp.status, 'stage_message': 'Subscribed to comparison events'})}\n\n"
        if comp.status in ("ready", "failed"):
            yield f"data: {json.dumps({'comparison_id': comparison_id, 'status': comp.status, 'stage_message': 'Completed'})}\n\n"
            return

        async for event in subscribe_status_events(comparison_id):
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("status") in ("ready", "failed"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/comparisons/{comparison_id}/export")
@router.get("/api/comparisons/{comparison_id}/export")
async def export_comparison(comparison_id: str):
    """
    GET /comparisons/{id}/export: Exports comparison redline and risk report to Markdown.
    """
    with database.get_db() as db:
        comp = db.query(Comparison).filter(Comparison.id == comparison_id).first()
        if not comp:
            raise HTTPException(status_code=404, detail=f"Comparison '{comparison_id}' not found.")
        if comp.status != "ready" or not comp.json_data:
            raise HTTPException(status_code=400, detail="Comparison is not ready for export yet.")

        markdown_text = export_comparison_to_markdown(comp.json_data)
        return {
            "comparison_id": comp.id,
            "filename": f"contract_comparison_{comp.doc_a[:8]}_{comp.doc_b[:8]}.md",
            "markdown": markdown_text,
        }
