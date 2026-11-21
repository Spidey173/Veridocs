"""
Session and file storage utilities for Veridocs.
"""

import logging
from pathlib import Path
from typing import Tuple
from fastapi import HTTPException, UploadFile

from config import get_settings

logger = logging.getLogger(__name__)


def safe_delete_file(file_path: Path) -> bool:
    """Safely delete a file ensuring it is within the uploads directory."""
    settings = get_settings()
    try:
        target = Path(file_path).resolve()
        base = Path(settings.UPLOAD_DIR).resolve()
        if base in target.parents or target == base:
            if target.is_file():
                target.unlink(missing_ok=True)
                return True
    except Exception as e:
        logger.warning(f"Error deleting file {file_path}: {e}")
    return False


async def save_upload_file_stream(
    file: UploadFile,
    max_bytes: int,
    file_id: str,
    ext: str,
) -> Tuple[Path, int, bool]:
    """Stream-writes an UploadFile directly to disk in 1MB chunks."""
    settings = get_settings()
    save_path = settings.UPLOAD_DIR / f"{file_id}{ext}"
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

    return save_path, total_read, file_too_large


def validate_question(question: str) -> None:
    """Validate query input."""
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question.strip()) > 1000:
        raise HTTPException(status_code=400, detail="Question exceeds maximum length of 1000 characters.")
