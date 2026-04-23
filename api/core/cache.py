import time
import hashlib


class TTLCache:
    def __init__(self, ttl_seconds: int = 86400):
        self._store: dict[str, tuple[str, float]] = {}
        self._ttl = ttl_seconds

    def _key(self, question: str) -> str:
        return hashlib.sha256(question.strip().lower().encode()).hexdigest()

    def get(self, question: str) -> str | None:
        k = self._key(question)
        entry = self._store.get(k)
        if not entry:
            return None
        value, ts = entry
        if time.time() - ts > self._ttl:
            del self._store[k]
            return None
        return value

    def set(self, question: str, answer: str) -> None:
        self._store[self._key(question)] = (answer, time.time())

    def size(self) -> int:
        return len(self._store)

    def stats(self) -> dict:
        now = time.time()
        live = {k: v for k, v in self._store.items() if now - v[1] <= self._ttl}
        self._store = live
        return {"size": len(live), "ttl_seconds": self._ttl}


answer_cache = TTLCache(ttl_seconds=86400)
