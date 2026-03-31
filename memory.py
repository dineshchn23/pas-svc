from threading import Lock
from typing import Dict, Optional
from datetime import datetime, timedelta


class InMemoryStore:
    def __init__(self):
        self._lock = Lock()
        self._store = {}
        self._session_state = {}  # Structured session state: {session_id: {last_intent, last_ticker, ...}}
        self._session_expiry = {}  # Track session expiry for cleanup

    def set(self, key, value):
        with self._lock:
            self._store[key] = value

    def get(self, key, default=None):
        with self._lock:
            return self._store.get(key, default)

    def append_chat_message(self, session_id, message, max_messages=20):
        with self._lock:
            key = f'chat:{session_id}'
            history = list(self._store.get(key, []))
            history.append(message)
            if max_messages > 0 and len(history) > max_messages:
                history = history[-max_messages:]
            self._store[key] = history
            # Initialize session state if needed
            if session_id not in self._session_state:
                self._session_state[session_id] = {}
            self._session_expiry[session_id] = datetime.now() + timedelta(hours=24)
            return list(history)

    def get_chat_history(self, session_id):
        with self._lock:
            key = f'chat:{session_id}'
            return list(self._store.get(key, []))

    def clear_chat_history(self, session_id):
        with self._lock:
            key = f'chat:{session_id}'
            if key in self._store:
                del self._store[key]

    def update_session_state(self, session_id: str, state: Dict) -> None:
        """Update structured session state for portfolio follow-up context."""
        with self._lock:
            if session_id not in self._session_state:
                self._session_state[session_id] = {}
            self._session_state[session_id].update(state)
            # Keep only portfolio-specific state keys to limit size
            keep_keys = {
                'last_intent', 'last_ticker', 'last_tickers', 'last_sectors',
                'portfolio_summary', 'last_risk_summary', 'last_compliance_status',
            }
            if len(self._session_state[session_id]) > len(keep_keys):
                current_keys = set(self._session_state[session_id].keys())
                for key in current_keys - keep_keys:
                    del self._session_state[session_id][key]
            self._session_expiry[session_id] = datetime.now() + timedelta(hours=24)

    def get_session_state(self, session_id: str) -> Dict:
        """Retrieve structured session state."""
        with self._lock:
            # Cleanup expired sessions
            now = datetime.now()
            expired = [sid for sid, expiry in self._session_expiry.items() if expiry < now]
            for sid in expired:
                self._session_state.pop(sid, None)
                self._session_expiry.pop(sid, None)
            
            return dict(self._session_state.get(session_id, {}))

    def clear_session(self, session_id: str) -> None:
        """Clear all session data."""
        with self._lock:
            key = f'chat:{session_id}'
            if key in self._store:
                del self._store[key]
            if session_id in self._session_state:
                del self._session_state[session_id]
            if session_id in self._session_expiry:
                del self._session_expiry[session_id]


store = InMemoryStore()
