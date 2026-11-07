import logging
import uuid
import threading
from datetime import datetime
from typing import List, Dict, Optional
from collections import OrderedDict

from models import ConversationMessage, MessageRole, CitationInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConversationManager:
    """Stores chat message history for each session."""

    def __init__(self, max_sessions: int = 200):
        self._conversations: OrderedDict[str, List[ConversationMessage]] = OrderedDict()
        self._max_sessions = max_sessions
        self._lock = threading.Lock()

    def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        citations: Optional[List[CitationInfo]] = None,
        confidence_score: Optional[float] = None
    ) -> ConversationMessage:
        """Add a new message to the session history."""
        with self._lock:
            if session_id not in self._conversations:
                self._conversations[session_id] = []
                self._evict_if_needed()

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
        """Get the recent message history for a session."""
        with self._lock:
            messages = list(self._conversations.get(session_id, []))
        return messages[-limit:]

    def get_history_for_prompt(
        self,
        session_id: str,
        limit: int = 6
    ) -> List[Dict[str, str]]:
        """Format recent messages for the LLM prompt."""
        messages = self.get_history(session_id, limit)
        return [
            {"role": msg.role.value, "content": msg.content}
            for msg in messages
        ]

    def clear_session(self, session_id: str):
        """Remove a session's history."""
        with self._lock:
            if session_id in self._conversations:
                del self._conversations[session_id]
                logger.info(f"Cleared conversation for session {session_id[:8]}")

    def clear_history(self, session_id: str):
        self.clear_session(session_id)

    def _evict_if_needed(self):
        """Remove the oldest session if we exceed max capacity."""
        while len(self._conversations) > self._max_sessions:
            oldest_key, _ = self._conversations.popitem(last=False)
            logger.info(f"Evicted conversation for session {oldest_key[:8]}")

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._conversations)


_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """Get or create the global ConversationManager."""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager
