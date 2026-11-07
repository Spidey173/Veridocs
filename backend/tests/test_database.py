import os
import json
import time
import pytest
import numpy as np
from dotenv import load_dotenv

import database
from config import get_settings


class MockConnection:
    def __init__(self, storage):
        self.storage = storage

    async def execute(self, query: str, *args):
        if "INSERT INTO sessions" in query:
            self.storage["sessions"][args[0]] = {
                "id": args[0],
                "owner_id": args[1],
                "file_names": args[2],
                "file_paths": args[3],
                "metadata": args[4],
                "insights": args[5],
                "created_at": args[6],
                "updated_at": args[7],
            }
        elif "DELETE FROM sessions" in query:
            self.storage["sessions"].pop(args[0], None)
            self.storage["chunks"].pop(args[0], None)
            self.storage["messages"].pop(args[0], None)
        elif "INSERT INTO chat_messages" in query:
            session_id = args[1]
            if session_id not in self.storage["messages"]:
                self.storage["messages"][session_id] = []
            self.storage["messages"][session_id].append({
                "id": args[0],
                "session_id": args[1],
                "role": args[2],
                "content": args[3],
                "created_at": args[4],
                "metadata": args[5],
            })
        return "OK"

    async def executemany(self, query: str, records):
        if "INSERT INTO document_chunks" in query:
            for rec in records:
                session_id = rec[0]
                if session_id not in self.storage["chunks"]:
                    self.storage["chunks"][session_id] = []
                self.storage["chunks"][session_id].append({
                    "id": len(self.storage["chunks"][session_id]) + 1,
                    "session_id": rec[0],
                    "source_file": rec[1],
                    "page_number": rec[2],
                    "chunk_index": rec[3],
                    "text": rec[4],
                    "metadata": rec[5],
                    "embedding": rec[6],
                })
        return "OK"

    async def fetchrow(self, query: str, *args):
        if "FROM sessions WHERE id = $1" in query:
            return self.storage["sessions"].get(args[0])
        return None

    async def fetch(self, query: str, *args):
        if "FROM document_chunks" in query:
            session_id = args[0]
            chunks = self.storage["chunks"].get(session_id, [])
            if "rrf_score" in query or "bm25_score" in query or "dense_score" in query or "LIMIT" in query:
                res = []
                for c in chunks:
                    row = dict(c)
                    row["dense_score"] = 0.95
                    row["sparse_score"] = 0.85
                    row["rrf_score"] = 0.90
                    res.append(row)
                return res
            return chunks
        elif "FROM chat_messages" in query:
            session_id = args[0]
            return self.storage["messages"].get(session_id, [])
        return []


class MockPool:
    def __init__(self):
        self.storage = {"sessions": {}, "chunks": {}, "messages": {}}

    def acquire(self):
        storage = self.storage

        class ContextManager:
            async def __aenter__(self):
                return MockConnection(storage)

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return ContextManager()

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_database_postgres_integration():
    """Verify PostgreSQL + pgvector integration with live database or simulated asyncpg pool."""
    settings = get_settings()
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        settings.DATABASE_URL = db_url

    ok = await database.init_db()
    if not ok:
        database._pool = MockPool()

    # 1. Test saving and retrieving session
    test_session_id = "test-postgres-session-123"
    await database.delete_session(test_session_id)

    save_ok = await database.save_session(
        session_id=test_session_id,
        owner_id="test_user_neon",
        file_names=["contract.pdf"],
        file_paths=["/tmp/contract.pdf"],
        metadata=[{"name": "contract.pdf", "pages": 2}],
        insights={"summary": "Sample test agreement."}
    )
    assert save_ok is True

    loaded_session = await database.get_session(test_session_id)
    assert loaded_session is not None
    assert loaded_session["session_id"] == test_session_id
    assert loaded_session["owner_id"] == "test_user_neon"
    assert "contract.pdf" in loaded_session["file_names"]

    # 2. Test saving chunks and pgvector search
    chunks = [
        {
            "text": "The payment shall be completed within thirty calendar days.",
            "page": 1,
            "chunk_index": 0,
            "source_file": "contract.pdf"
        },
        {
            "text": "The agreement is governed by the state laws of Delaware.",
            "page": 2,
            "chunk_index": 1,
            "source_file": "contract.pdf"
        }
    ]
    v1 = np.random.randn(384).astype(np.float32)
    v1 /= np.linalg.norm(v1)
    v2 = np.random.randn(384).astype(np.float32)
    v2 /= np.linalg.norm(v2)
    embeddings = np.stack([v1, v2])

    chunks_ok = await database.save_chunks(test_session_id, chunks, embeddings)
    assert chunks_ok is True

    # 3. Test retrieving chunks with embeddings
    loaded_chunks = await database.get_chunks_for_session(test_session_id, include_embeddings=True)
    assert len(loaded_chunks) == 2
    assert loaded_chunks[0]["text"] == chunks[0]["text"]

    # 4. Test hybrid search with pgvector + FTS
    results = await database.hybrid_search_postgres(
        session_id=test_session_id,
        query="payment calendar days",
        query_embedding=v1,
        k=2
    )
    assert len(results) > 0
    assert results[0]["page"] == 1

    # 5. Test chat message persistence
    msg_ok = await database.save_chat_message(
        session_id=test_session_id,
        message_id="msg-1",
        role="user",
        content="What are the payment terms?"
    )
    assert msg_ok is True

    history = await database.get_chat_history(test_session_id)
    assert len(history) == 1
    assert history[0]["content"] == "What are the payment terms?"

    # 6. Clean up
    del_ok = await database.delete_session(test_session_id)
    assert del_ok is True

    await database.close_db()
