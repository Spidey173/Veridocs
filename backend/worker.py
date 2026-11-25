"""
Worker entrypoint for Veridocs task queue (RQ / Threaded).
Run via:
    python -m worker
    or
    python backend/worker.py
"""

import sys
import logging
from pathlib import Path

# Ensure backend is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from config import get_settings
from queue_service import get_redis_client
import database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [Worker] %(message)s")
logger = logging.getLogger("veridocs-worker")


def run_worker():
    settings = get_settings()
    logger.info("Starting Veridocs Background Processing Worker...")
    database.init_db()

    client = get_redis_client()
    if client:
        try:
            from rq import Worker as RQWorker, Queue as RQQueue

            q = RQQueue(settings.QUEUE_NAME, connection=client)
            worker = RQWorker([q], connection=client)
            logger.info(f"Worker listening on Redis queue: '{settings.QUEUE_NAME}'")
            worker.work(with_scheduler=True)
            return
        except Exception as e:
            logger.error(f"RQ Worker encountered error: {e}. Exiting.")
            sys.exit(1)
    else:
        logger.warning("No Redis connection found. Running in standalone thread executor mode.")


if __name__ == "__main__":
    run_worker()
