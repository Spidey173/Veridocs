"""
Background Job Processing endpoints for heavy filings (SEC 10-Ks, multi-hundred page PDFs).
"""

import time
import uuid
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, Form, Query, BackgroundTasks

from config import get_settings
from auth import get_current_user, UserContext, assert_resource_ownership
from models import JobResponse, JobDetailResponse, JobListResponse, JobProgress, JobStatus
from job_tracker import get_job_tracker
from tasks import dispatch_document_job
from rate_limiter import enforce_rate_limit
from session_store import sessions, _get_session, _safe_delete_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/jobs/upload", response_model=JobResponse, status_code=202)
@router.post("/upload/async", response_model=JobResponse, status_code=202)
async def submit_async_document_job(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    current_user: UserContext = Depends(get_current_user)
):
    """
    Submit heavy documents for asynchronous background processing via Celery and Redis.
    Immediately returns HTTP 202 Accepted with a job_id for non-blocking polling.
    """
    settings = get_settings()
    enforce_rate_limit(request, "async_upload", max_requests=settings.UPLOAD_RATE_LIMIT, window_seconds=60)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    saved_paths = []
    file_names = []
    failed_files = []

    for file in files:
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()

        if ext not in settings.ALLOWED_EXTENSIONS:
            failed_files.append(f"{filename} (unsupported type: {ext})")
            continue

        try:
            # Stream directly to disk in 1MB chunks to avoid memory spikes
            max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            session_file_id = str(uuid.uuid4())
            save_path = Path(settings.UPLOAD_DIR) / f"{session_file_id}{ext}"
            total_read = 0
            file_too_large = False

            with open(save_path, "wb") as out_f:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    total_read += len(chunk)
                    if total_read > max_bytes:
                        file_too_large = True
                        break
                    out_f.write(chunk)

            if file_too_large:
                failed_files.append(f"{filename} (exceeds {settings.MAX_FILE_SIZE_MB}MB limit)")
                _safe_delete_file(save_path)
                continue

            saved_paths.append(str(save_path))
            file_names.append(filename)
        except Exception as e:
            failed_files.append(f"{filename}: {str(e)}")

    if not saved_paths:
        err = "No valid files could be accepted for processing."
        if failed_files:
            err += f" Issues: {'; '.join(failed_files)}"
        raise HTTPException(status_code=400, detail=err)

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    tracker = get_job_tracker()
    tracker.create_job(
        job_id=job_id,
        file_names=file_names,
        file_paths=saved_paths,
        owner_id=current_user.user_id,
        session_id=session_id
    )

    dispatch_document_job(
        job_id=job_id,
        file_paths=saved_paths,
        file_names=file_names,
        owner_id=current_user.user_id,
        session_id=session_id,
        background_tasks=background_tasks
    )

    logger.info(f"Accepted job {job_id} for user {current_user.user_id} with {len(file_names)} file(s)")

    msg = f"Document queued for processing. Track progress via GET /api/jobs/{job_id}"
    if failed_files:
        msg += f" Note: {len(failed_files)} file(s) skipped."

    return JobResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        created_at=time.time(),
        file_names=file_names,
        message=msg
    )


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job_status(
    job_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Check the status of a background processing job."""
    tracker = get_job_tracker()
    job = tracker.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    assert_resource_ownership(
        resource_owner_id=job.get("owner_id"),
        current_user=current_user,
        resource_type="job",
        action="view"
    )

    session_id = job.get("session_id")
    if session_id and session_id not in sessions:
        try:
            await _get_session(session_id, current_user)
        except Exception as e:
            logger.debug(f"Session {session_id} not available yet for job {job_id}: {e}")

    progress_obj = JobProgress.from_dict(job.get("progress"))

    return JobDetailResponse(
        job_id=job["job_id"],
        status=job.get("status", JobStatus.QUEUED),
        owner_id=job.get("owner_id", "unknown"),
        created_at=job.get("created_at", time.time()),
        updated_at=job.get("updated_at", time.time()),
        file_names=job.get("file_names", []),
        progress=progress_obj,
        session_id=session_id,
        error=job.get("error"),
        result_summary=job.get("result_summary")
    )


@router.get("/jobs", response_model=JobListResponse)
async def list_user_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserContext = Depends(get_current_user)
):
    """List asynchronous processing jobs for the authenticated user."""
    tracker = get_job_tracker()
    raw_jobs = tracker.list_jobs(owner_id=current_user.user_id, limit=limit)
    job_responses = []

    for j in raw_jobs:
        progress_obj = JobProgress.from_dict(j.get("progress"))
        job_responses.append(JobDetailResponse(
            job_id=j["job_id"],
            status=j.get("status", JobStatus.QUEUED),
            owner_id=j.get("owner_id", "unknown"),
            created_at=j.get("created_at", time.time()),
            updated_at=j.get("updated_at", time.time()),
            file_names=j.get("file_names", []),
            progress=progress_obj,
            session_id=j.get("session_id"),
            error=j.get("error"),
            result_summary=j.get("result_summary")
        ))

    return JobListResponse(jobs=job_responses, total=len(job_responses))


@router.delete("/jobs/{job_id}")
async def delete_or_cancel_job(
    job_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Cancel or delete a background job and clean up its staging files."""
    tracker = get_job_tracker()
    job = tracker.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    assert_resource_ownership(
        resource_owner_id=job.get("owner_id"),
        current_user=current_user,
        resource_type="job",
        action="delete"
    )

    for p in job.get("file_paths", []):
        try:
            Path(p).unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"Could not remove staged file {p}: {e}")

    tracker.delete_job(job_id)
    return {"status": "deleted", "job_id": job_id}
