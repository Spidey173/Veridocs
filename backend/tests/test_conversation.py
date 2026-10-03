"""
Unit tests for conversation.py ConversationManager.
"""

import pytest
from conversation import ConversationManager, get_conversation_manager
from models import MessageRole, CitationInfo


class TestConversationManager:
    def test_add_and_get_messages(self):
        """Verify adding messages and retrieving session history."""
        mgr = ConversationManager(max_sessions=10)
        session_id = "sess-test-1"

        citation = CitationInfo(
            citation_id=1,
            page=2,
            source_file="test.pdf",
            highlighted_text="Some text",
        )

        msg1 = mgr.add_message(
            session_id=session_id,
            role=MessageRole.USER,
            content="Hello AI",
        )
        assert msg1.role == MessageRole.USER
        assert msg1.content == "Hello AI"
        assert msg1.id is not None

        msg2 = mgr.add_message(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="Hello user [Page 2]",
            citations=[citation],
            confidence_score=0.95,
        )
        assert msg2.role == MessageRole.ASSISTANT
        assert msg2.citations == [citation]
        assert msg2.confidence_score == 0.95

        history = mgr.get_history(session_id)
        assert len(history) == 2
        assert history[0].content == "Hello AI"
        assert history[1].content == "Hello user [Page 2]"

    def test_get_history_limit(self):
        """Verify history limit slicing."""
        mgr = ConversationManager()
        session_id = "sess-limit"

        for i in range(10):
            mgr.add_message(
                session_id=session_id,
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=f"Message {i}",
            )

        history_5 = mgr.get_history(session_id, limit=5)
        assert len(history_5) == 5
        assert history_5[0].content == "Message 5"
        assert history_5[-1].content == "Message 9"

    def test_get_history_for_prompt(self):
        """Verify simplified prompt formatting."""
        mgr = ConversationManager()
        session_id = "sess-prompt"

        mgr.add_message(session_id, MessageRole.USER, "Question 1")
        mgr.add_message(session_id, MessageRole.ASSISTANT, "Answer 1")

        prompt_history = mgr.get_history_for_prompt(session_id)
        assert prompt_history == [
            {"role": "user", "content": "Question 1"},
            {"role": "assistant", "content": "Answer 1"},
        ]

    def test_clear_session(self):
        """Verify clearing conversation history."""
        mgr = ConversationManager()
        session_id = "sess-clear"
        mgr.add_message(session_id, MessageRole.USER, "Clear me")
        assert mgr.active_count == 1

        mgr.clear_session(session_id)
        assert mgr.active_count == 0
        assert mgr.get_history(session_id) == []

    def test_lru_eviction(self):
        """Verify LRU eviction when max_sessions is reached."""
        mgr = ConversationManager(max_sessions=3)

        mgr.add_message("sess-1", MessageRole.USER, "msg1")
        mgr.add_message("sess-2", MessageRole.USER, "msg2")
        mgr.add_message("sess-3", MessageRole.USER, "msg3")
        assert mgr.active_count == 3

        # Access sess-1 to mark it most recently used
        mgr.add_message("sess-1", MessageRole.ASSISTANT, "reply1")

        # Adding sess-4 should evict sess-2 (since sess-1 was refreshed)
        mgr.add_message("sess-4", MessageRole.USER, "msg4")
        assert mgr.active_count == 3
        assert len(mgr.get_history("sess-2")) == 0
        assert len(mgr.get_history("sess-1")) == 2
        assert len(mgr.get_history("sess-3")) == 1
        assert len(mgr.get_history("sess-4")) == 1

    def test_singleton_getter(self):
        """Verify get_conversation_manager returns global instance."""
        cm1 = get_conversation_manager()
        cm2 = get_conversation_manager()
        assert cm1 is cm2
