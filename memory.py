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

    # Chat-specific message history APIs removed with chat feature.

    def update_session_state(self, session_id: str, state: Dict) -> None:
        """Update structured session state for follow-up context."""
        with self._lock:
            if session_id not in self._session_state:
                self._session_state[session_id] = {}
            self._session_state[session_id].update(state)
            # Limit state size
            if len(self._session_state[session_id]) > 20:
                # Keep only recent/important keys
                keep_keys = {'last_intent', 'last_ticker', 'last_tickers', 'last_sectors', 'last_topic', 'portfolio_summary'}
                current_keys = set(self._session_state[session_id].keys())
                for key in current_keys - keep_keys:
                    if len(self._session_state[session_id]) <= 20:
                        break
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
            # session-scoped store cleared
            keys_to_delete = [k for k in self._store.keys() if k.startswith(f'session:{session_id}') or k.startswith(f'chat:{session_id}')]
            for k in keys_to_delete:
                del self._store[k]
            if session_id in self._session_state:
                del self._session_state[session_id]
            if session_id in self._session_expiry:
                del self._session_expiry[session_id]


store = InMemoryStore()
