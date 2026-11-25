"""
Queue and Event Bus for Veridocs background task processing.
Uses Redis when available, with an automatic in-memory background worker fallback for testing.
"""

import json
import logging
import time
import threading
from typing import Dict, List, Any, Callable, Generator
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor

from config import get_settings

logger = logging.getLogger(__name__)

# In-memory bus for SSE events when Redis is unavailable or for local tests
_local_event_subscribers: Dict[str, List[Queue]] = {}
_subscribers_lock = threading.Lock()
_local_executor = ThreadPoolExecutor(max_workers=4)

_redis_client = None
_redis_checked = False


def get_redis_client():
    global _redis_client, _redis_checked
    if not _redis_checked:
        settings = get_settings()
        try:
            import redis

            client = redis.from_url(settings.REDIS_URL, socket_timeout=2.0, socket_connect_timeout=2.0)
            client.ping()
            _redis_client = client
            logger.info(f"Connected to Redis at {settings.REDIS_URL}")
        except Exception as e:
            logger.info(f"Redis not reachable ({e}). Using in-memory task executor and event bus.")
            _redis_client = None
        _redis_checked = True
    return _redis_client


def publish_status_event(document_id: str, event_data: Dict[str, Any]):
    """Publish a status transition event to Redis or in-memory queues."""
    event_data["timestamp"] = event_data.get("timestamp", time.time())
    event_data["document_id"] = document_id
    payload = json.dumps(event_data)

    client = get_redis_client()
    if client:
        try:
            client.publish(f"veridocs:doc:{document_id}", payload)
            # Cache the latest status in Redis with a 1 hour TTL
            client.set(f"veridocs:status:{document_id}", payload, ex=3600)
            return
        except Exception as e:
            logger.warning(f"Failed to publish to Redis: {e}")

    # Fallback to local subscriber queues
    with _subscribers_lock:
        queues = _local_event_subscribers.get(document_id, [])
        for q in list(queues):
            try:
                q.put_nowait(event_data)
            except Exception:
                pass


def subscribe_status_events(document_id: str) -> Generator[Dict[str, Any], None, None]:
    """Yield status events for a document until terminal state (ready or failed)."""
    import database

    doc = database.get_document(document_id)
    if doc:
        yield {
            "document_id": document_id,
            "status": doc["status"],
            "error": doc.get("error"),
            "page_count": doc.get("page_count", 0),
        }
        if doc["status"] in ("ready", "failed"):
            return

    client = get_redis_client()
    if client:
        pubsub = client.pubsub()
        pubsub.subscribe(f"veridocs:doc:{document_id}")
        try:
            for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        yield data
                        if data.get("status") in ("ready", "failed"):
                            break
                    except Exception:
                        pass
        finally:
            try:
                pubsub.unsubscribe()
                pubsub.close()
            except Exception:
                pass
        return

    # In-memory fallback
    q: Queue = Queue()
    with _subscribers_lock:
        if document_id not in _local_event_subscribers:
            _local_event_subscribers[document_id] = []
        _local_event_subscribers[document_id].append(q)

    try:
        while True:
            try:
                item = q.get(timeout=30.0)
                yield item
                if item.get("status") in ("ready", "failed"):
                    break
            except Empty:
                # Heartbeat or check DB status
                doc_current = database.get_document(document_id)
                if doc_current and doc_current["status"] in ("ready", "failed"):
                    yield {
                        "document_id": document_id,
                        "status": doc_current["status"],
                        "error": doc_current.get("error"),
                    }
                    break
    finally:
        with _subscribers_lock:
            if document_id in _local_event_subscribers:
                if q in _local_event_subscribers[document_id]:
                    _local_event_subscribers[document_id].remove(q)
                if not _local_event_subscribers[document_id]:
                    del _local_event_subscribers[document_id]


def enqueue_task(func: Callable, *args, **kwargs):
    """Enqueue a job to RQ or local background thread pool."""
    client = get_redis_client()
    settings = get_settings()

    if client:
        try:
            from rq import Queue as RQQueue

            q = RQQueue(settings.QUEUE_NAME, connection=client)
            job = q.enqueue(func, *args, **kwargs, retry=3)
            logger.info(f"Enqueued job {job.id} to RQ")
            return job.id
        except Exception as e:
            logger.warning(f"RQ enqueue failed ({e}), falling back to background thread.")

    # Fallback to threaded executor
    _local_executor.submit(func, *args, **kwargs)
    return "local-thread"
