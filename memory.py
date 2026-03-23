from threading import Lock

class InMemoryStore:
    def __init__(self):
        self._lock = Lock()
        self._store = {}

    def set(self, key, value):
        with self._lock:
            self._store[key] = value

    def get(self, key, default=None):
        with self._lock:
            return self._store.get(key, default)

store = InMemoryStore()
