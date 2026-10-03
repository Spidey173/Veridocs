"""
Conversation memory manager for DocuMind AI.
Stores multi-turn conversation history per session.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from collections import OrderedDict

from models import ConversationMessage, MessageRole, CitationInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConversationManager:
    """
    In-memory conversation store with LRU eviction.
    Tracks message history, citations, and confidence scores per session.

    Designed to be replaced with PostgreSQL in Phase 3.
    """

    def __init__(self, max_sessions: int = 200):
        self._conversations: OrderedDict[str, List[ConversationMessage]] = OrderedDict()
        self._max_sessions = max_sessions

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        citations: Optional[List[CitationInfo]] = None,
        confidence_score: Optional[float] = None
    ) -> ConversationMessage:
        """Add a message to the conversation history."""
        if session_id not in self._conversations:
            self._conversations[session_id] = []
            self._evict_if_needed()

        # Move to end (most recently used)
        self._conversations.move_to_end(session_id)

        message = ConversationMessage(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            citations=citations,
            confidence_score=confidence_score,
            timestamp=datetime.utcnow()
        )

        self._conversations[session_id].append(message)
        return message

    def get_history(
        self,
        session_id: str,
        limit: int = 20
    ) -> List[ConversationMessage]:
        """Get conversation history for a session."""
        messages = self._conversations.get(session_id, [])
        return messages[-limit:]

    def get_history_for_prompt(
        self,
        session_id: str,
        limit: int = 6
    ) -> List[Dict[str, str]]:
        """
        Get conversation history formatted for LLM prompt inclusion.
        Returns simplified dicts with role and content.
        """
        messages = self.get_history(session_id, limit)
        return [
            {"role": msg.role.value, "content": msg.content}
            for msg in messages
        ]

    def clear_session(self, session_id: str):
        """Clear conversation history for a session."""
        if session_id in self._conversations:
            del self._conversations[session_id]
            logger.info(f"Cleared conversation for session {session_id[:8]}")

    def _evict_if_needed(self):
        """Evict oldest session if over capacity."""
        while len(self._conversations) > self._max_sessions:
            oldest_key, _ = self._conversations.popitem(last=False)
            logger.info(f"Evicted conversation for session {oldest_key[:8]}")

    @property
    def active_count(self) -> int:
        return len(self._conversations)


# Global conversation manager singleton
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """Get the global conversation manager singleton."""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager
