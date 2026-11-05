"""
Job status tracking manager for Veridocs async document processing.
Supports distributed Redis state caching with local memory and disk persistence fallbacks.
"""

import os
import json
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import lru_cache

from config import get_settings

logger = logging.getLogger(__name__)


class JobTracker:
    """
    Manages document processing background job lifecycle.
    Stores job metadata, progress telemetry, owner verification, and results.
    """

    def __init__(self):
        self.settings = get_settings()
        self._lock = threading.Lock()
        self._memory_jobs: Dict[str, Dict[str, Any]] = {}
        self._jobs_dir = Path(self.settings.UPLOAD_DIR) / "jobs"
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._redis_client = None
        self._init_redis()

    def _init_redis(self):
        """Attempt initializing connection to Redis backend if available."""
        try:
            import redis
            client = redis.from_url(
                self.settings.CELERY_RESULT_BACKEND,
                socket_timeout=0.8,
                socket_connect_timeout=0.8,
            )
            if client.ping():
                self._redis_client = client
                logger.info(f"JobTracker connected to Redis at {self.settings.CELERY_RESULT_BACKEND}")
        except Exception as e:
            logger.debug(f"JobTracker using local memory/disk storage (Redis unavailable: {e})")
            self._redis_client = None

    def _save_to_disk(self, job_data: Dict[str, Any]):
        """Persist job record to disk."""
        try:
            job_id = job_data["job_id"]
            job_file = self._jobs_dir / f"{job_id}.json"
            with open(job_file, "w", encoding="utf-8") as f:
                json.dump(job_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist job {job_data.get('job_id')} to disk: {e}")

    def _save_to_redis(self, job_data: Dict[str, Any]):
        """Save job state to Redis with 24-hour expiration."""
        if not self._redis_client:
            return
        try:
            key = f"veridocs:job:{job_data['job_id']}"
            self._redis_client.setex(key, 86400, json.dumps(job_data))
        except Exception as e:
            logger.warning(f"Failed to update job in Redis: {e}")

    def create_job(
        self,
        job_id: str,
        file_names: List[str],
        file_paths: List[str],
        owner_id: str,
        session_id: Optional[str] = None,
        total_pages: int = 0
    ) -> Dict[str, Any]:
        """Initialize a new job record with queued status."""
        now = time.time()
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "owner_id": owner_id,
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "file_names": file_names,
            "file_paths": file_paths,
            "progress": {
                "current_page": 0,
                "total_pages": total_pages,
                "percent": 0.0,
                "stage": "Job queued for processing",
                "scanned_pages": 0,
                "chunks_created": 0,
            },
            "result_summary": None,
            "error": None,
        }

        with self._lock:
            self._memory_jobs[job_id] = job_data

        self._save_to_redis(job_data)
        self._save_to_disk(job_data)
        return job_data

    def update_progress(
        self,
        job_id: str,
        percent: Optional[float] = None,
        stage: Optional[str] = None,
        current_page: Optional[int] = None,
        total_pages: Optional[int] = None,
        scanned_pages: Optional[int] = None,
        chunks_created: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update job stage, percentage, and page counts."""
        job = self.get_job(job_id)
        if not job:
            return None

        with self._lock:
            now = time.time()
            job["updated_at"] = now
            if job["status"] == "queued":
                job["status"] = "processing"

            prog = job.get("progress", {})
            if percent is not None:
                prog["percent"] = min(100.0, max(0.0, percent))
            if stage is not None:
                prog["stage"] = stage
            if current_page is not None:
                prog["current_page"] = current_page
            if total_pages is not None:
                prog["total_pages"] = total_pages
            if scanned_pages is not None:
                prog["scanned_pages"] = scanned_pages
            if chunks_created is not None:
                prog["chunks_created"] = chunks_created

            job["progress"] = prog
            self._memory_jobs[job_id] = job

        self._save_to_redis(job)
        self._save_to_disk(job)
        return job

    def complete_job(
        self,
        job_id: str,
        session_id: str,
        result_summary: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Mark job as successfully completed."""
        job = self.get_job(job_id)
        if not job:
            return None

        with self._lock:
            now = time.time()
            job["updated_at"] = now
            job["status"] = "completed"
            job["session_id"] = session_id
            job["result_summary"] = result_summary or {}
            job["progress"]["percent"] = 100.0
            job["progress"]["stage"] = "Document processing complete"
            self._memory_jobs[job_id] = job

        self._save_to_redis(job)
        self._save_to_disk(job)
        return job

    def fail_job(self, job_id: str, error_message: str) -> Optional[Dict[str, Any]]:
        """Mark job as failed with an error message."""
        job = self.get_job(job_id)
        if not job:
            return None

        with self._lock:
            now = time.time()
            job["updated_at"] = now
            job["status"] = "failed"
            job["error"] = error_message
            job["progress"]["stage"] = f"Failed: {error_message}"
            self._memory_jobs[job_id] = job

        self._save_to_redis(job)
        self._save_to_disk(job)
        return job

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve job from memory, Redis, or disk storage."""
        with self._lock:
            if job_id in self._memory_jobs:
                return self._memory_jobs[job_id]

        # Check Redis
        if self._redis_client:
            try:
                raw = self._redis_client.get(f"veridocs:job:{job_id}")
                if raw:
                    data = json.loads(raw)
                    with self._lock:
                        self._memory_jobs[job_id] = data
                    return data
            except Exception as e:
                logger.debug(f"Redis get error for job {job_id}: {e}")

        # Check Disk
        job_file = self._jobs_dir / f"{job_id}.json"
        if job_file.exists():
            try:
                with open(job_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with self._lock:
                    self._memory_jobs[job_id] = data
                return data
            except Exception as e:
                logger.error(f"Error reading job file {job_file}: {e}")

        return None

    def list_jobs(self, owner_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """List active and historical jobs, filtered by owner if provided."""
        all_jobs: Dict[str, Dict[str, Any]] = {}

        # 1. From memory
        with self._lock:
            all_jobs.update(self._memory_jobs)

        # 2. From disk
        try:
            for p in self._jobs_dir.glob("*.json"):
                jid = p.stem
                if jid not in all_jobs:
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            all_jobs[jid] = json.load(f)
                    except Exception:
                        pass
        except Exception:
            pass

        jobs_list = list(all_jobs.values())
        if owner_id:
            jobs_list = [j for j in jobs_list if j.get("owner_id") == owner_id]

        jobs_list.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return jobs_list[:limit]

    def delete_job(self, job_id: str) -> bool:
        """Remove a job record from memory, Redis, and disk."""
        with self._lock:
            self._memory_jobs.pop(job_id, None)

        if self._redis_client:
            try:
                self._redis_client.delete(f"veridocs:job:{job_id}")
            except Exception:
                pass

        job_file = self._jobs_dir / f"{job_id}.json"
        if job_file.exists():
            try:
                job_file.unlink()
            except Exception:
                pass

        return True

    def clear(self):
        """Reset all in-memory and disk jobs (for testing)."""
        with self._lock:
            self._memory_jobs.clear()
        if self._redis_client:
            try:
                keys = self._redis_client.keys("veridocs:job:*")
                if keys:
                    self._redis_client.delete(*keys)
            except Exception:
                pass
        try:
            for p in self._jobs_dir.glob("*.json"):
                try:
                    p.unlink()
                except Exception:
                    pass
        except Exception:
            pass


@lru_cache()
def get_job_tracker() -> JobTracker:
    """Singleton getter for JobTracker instance."""
    return JobTracker()
