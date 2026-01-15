"""Thread-safe in-memory store for conversation sessions.

Optimized for minimal latency (<10ms operations) to stay within Alexa's 8-second deadline.
"""

import os
import threading
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ConversationTurn:
    """A single turn in a conversation (user query + assistant response)."""
    query: str
    response: str
    domain: str  # tasks, contacts, general
    timestamp: float = field(default_factory=time.time)


@dataclass
class Session:
    """A conversation session with multiple turns."""
    session_id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


class ConversationStore:
    """Thread-safe in-memory store for conversation sessions.

    Performance characteristics:
    - O(1) session lookup by session_id (dict-based)
    - Lazy cleanup: expired sessions removed during access, no background threads
    - Minimal lock scope: no I/O operations inside lock
    - Sliding window: keeps only last N turns per session
    """

    def __init__(
        self,
        max_turns: int = None,
        ttl_seconds: int = None,
        max_sessions: int = 100
    ):
        """Initialize the conversation store.

        Args:
            max_turns: Max turns to keep per session (default from env or 5)
            ttl_seconds: Session TTL in seconds (default from env or 120)
            max_sessions: Max concurrent sessions before cleanup
        """
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._max_turns = max_turns or int(os.getenv("CONVERSATION_MAX_TURNS", "5"))
        self._ttl = ttl_seconds or int(os.getenv("CONVERSATION_TTL_SECONDS", "120"))
        self._max_sessions = max_sessions

    def get_conversation_history(self, session_id: str) -> List[ConversationTurn]:
        """Get conversation history for a session. Thread-safe.

        Returns empty list if session doesn't exist or has expired.
        This is the primary read operation - optimized for speed.
        """
        if not session_id:
            return []

        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []

            # Check if expired
            if time.time() - session.last_activity > self._ttl:
                del self._sessions[session_id]
                return []

            # Update activity timestamp
            session.last_activity = time.time()

            # Return copy to avoid mutation issues
            return list(session.turns)

    def add_turn(
        self,
        session_id: str,
        query: str,
        response: str,
        domain: str
    ) -> None:
        """Add a conversation turn to a session. Thread-safe.

        Creates session if it doesn't exist.
        Maintains sliding window of max_turns.
        """
        if not session_id:
            return

        turn = ConversationTurn(
            query=query,
            response=response,
            domain=domain
        )

        with self._lock:
            # Periodic cleanup (every ~10 accesses on average)
            if len(self._sessions) > self._max_sessions:
                self._cleanup_expired_sessions()

            if session_id not in self._sessions:
                self._sessions[session_id] = Session(session_id=session_id)

            session = self._sessions[session_id]
            session.last_activity = time.time()
            session.turns.append(turn)

            # Sliding window: keep only last N turns
            if len(session.turns) > self._max_turns:
                session.turns = session.turns[-self._max_turns:]

    def clear_session(self, session_id: str) -> None:
        """Clear a specific session. Thread-safe."""
        if not session_id:
            return

        with self._lock:
            self._sessions.pop(session_id, None)

    def _cleanup_expired_sessions(self) -> None:
        """Remove expired sessions. Must be called within lock."""
        now = time.time()

        # Find and remove expired sessions
        expired = [
            sid for sid, session in self._sessions.items()
            if now - session.last_activity > self._ttl
        ]

        for sid in expired:
            del self._sessions[sid]

        # If still over max, remove oldest sessions
        if len(self._sessions) > self._max_sessions:
            sorted_sessions = sorted(
                self._sessions.items(),
                key=lambda x: x[1].last_activity
            )
            excess = len(self._sessions) - self._max_sessions
            for sid, _ in sorted_sessions[:excess]:
                del self._sessions[sid]

    def get_stats(self) -> Dict:
        """Get store statistics (for debugging/monitoring)."""
        with self._lock:
            return {
                "active_sessions": len(self._sessions),
                "max_turns": self._max_turns,
                "ttl_seconds": self._ttl
            }
