import pytest
import numpy as np
import database
from config import get_settings


@pytest.mark.asyncio
async def test_database_postgres_integration():
    """Verify PostgreSQL + pgvector integration if DATABASE_URL is set in environment."""
    settings = get_settings()
    # Read the real DATABASE_URL from .env or os.environ for this integration test
    import os
    from dotenv import load_dotenv
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        pytest.skip("DATABASE_URL not configured. Skipping live PostgreSQL test.")

    settings.DATABASE_URL = db_url

    # 1. Initialize DB
    ok = await database.init_db()
    if not ok:
        pytest.skip("Could not reach PostgreSQL (network blocked or offline). Skipping live integration test.")
    assert ok is True

    # 2. Test saving and retrieving session
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

    # 3. Test saving chunks and pgvector search
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

    # 4. Test hybrid search with pgvector + FTS
    results = await database.hybrid_search_postgres(
        session_id=test_session_id,
        query="payment calendar days",
        query_embedding=v1,
        k=2
    )
    assert len(results) > 0
    assert results[0]["page"] == 1
    assert "payment" in results[0]["text"].lower()

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
