"""
Request-level cooperative cancellation for search execution.

Provides per-request `CancellationToken` instances managed by a thread-safe
`CancellationRegistry`. Cancellation is strictly cooperative between stages
and never forcibly interrupts running PyTorch/CUDA kernels or corrupts shared
model/Qdrant state.
"""
import threading
from typing import Dict


class SearchCancelledError(Exception):
    """Raised at a cooperative checkpoint when a search request has been cancelled."""

    def __init__(self, request_id: str, stage: str = ""):
        self.request_id = request_id
        self.stage = stage
        msg = f"Search request {request_id} cancelled"
        if stage:
            msg += f" at stage '{stage}'"
        super().__init__(msg)


class CancellationToken:
    """Thread-safe cooperative cancellation token scoped to a single search request."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def check(self, stage: str = "") -> None:
        if self._event.is_set():
            raise SearchCancelledError(self.request_id, stage=stage)


class CancellationRegistry:
    """
    Thread-safe registry tracking active search request cancellation tokens.
    Entries must be unregistered in a `finally` block to prevent memory leaks.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: Dict[str, CancellationToken] = {}

    def register(self, request_id: str) -> CancellationToken:
        with self._lock:
            token = CancellationToken(request_id)
            self._tokens[request_id] = token
            return token

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            token = self._tokens.get(request_id)
            if token is None:
                return False
            token.cancel()
            return True

    def unregister(self, request_id: str) -> None:
        with self._lock:
            self._tokens.pop(request_id, None)

    def active_count(self) -> int:
        with self._lock:
            return len(self._tokens)
