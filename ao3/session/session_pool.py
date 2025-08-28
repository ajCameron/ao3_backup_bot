# ao3/session_pool.py
from __future__ import annotations
import threading
from typing import Dict, Callable, Optional
import requests

from session.threadsafe import ThreadSafeSessionProxy
from ao3.requester import requester  # to install adapters/headers once

class SessionPool:
    """
    One underlying requests.Session per AO3 username, shared across wrappers.
    Completely opaque to library users.
    """
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_user: Dict[str, ThreadSafeSessionProxy] = {}

    def get_or_create(
        self,
        username: str,
        *,
        login_fn: Callable[[requests.Session], str],  # returns authenticity_token
        token_requests_per_window: int = 60,
        token_window_seconds: float = 60.0,
    ) -> ThreadSafeSessionProxy:
        with self._lock:
            proxy = self._by_user.get(username)
            if proxy is not None:
                return proxy

            raw = requests.Session()
            # install retries/adapters + polite defaults once
            requester.configure_session(raw)

            # Perform AO3 login using provided function; must return token
            token = login_fn(raw)

            proxy = ThreadSafeSessionProxy(
                raw,
                token_requests_per_window=token_requests_per_window,
                token_window_seconds=token_window_seconds,
            )
            proxy.set_token(token)
            self._by_user[username] = proxy
            return proxy

    def set_token(self, username: str, token: Optional[str]) -> None:
        with self._lock:
            if username in self._by_user:
                self._by_user[username].set_token(token)

    def drop(self, username: str) -> None:
        with self._lock:
            self._by_user.pop(username, None)

# module-level singleton
session_pool = SessionPool()
