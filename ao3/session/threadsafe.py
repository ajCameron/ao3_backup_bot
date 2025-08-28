# ao3/threadsafe.py

from __future__ import annotations

import threading
import time
from typing import Optional, Mapping, Any
import requests


class ThreadSafeSessionProxy:
    """
    Wraps a requests.Session:
      - Serializes .request() with an RLock
      - Applies a per-token throttle (token bucket) if a token is set
    """

    def __init__(
        self,
        session: requests.Session,
        token_requests_per_window: int = 60,
        token_window_seconds: float = 60.0,
    ) -> None:
        self._session = session
        self._lock = threading.RLock()

        # Per-token throttle
        self._token: Optional[str] = None
        self._tw = float(token_window_seconds)
        self._tcap = max(1, int(token_requests_per_window))
        self._tokens = float(self._tcap)   # start full
        self._last = time.monotonic()

    # ---- token mgmt ---------------------------------------------------------
    def set_token(self, token: Optional[str]) -> None:
        # Changing token also resets the bucket to "full" for the new key
        with self._lock:
            self._token = token
            self._tokens = float(self._tcap)
            self._last = time.monotonic()

    # ---- throttle -----------------------------------------------------------
    def _throttle_token(self) -> None:
        # Only throttle if we actually have a token
        if self._token is None:
            return
        now = time.monotonic()
        elapsed = now - self._last
        self._last = now
        # refill
        self._tokens = min(self._tcap, self._tokens + elapsed * (self._tcap / self._tw))
        if self._tokens < 1.0:
            sleep_for = (1.0 - self._tokens) * (self._tw / self._tcap)
            time.sleep(sleep_for)
            self._tokens = 0.0
        # consume one
        self._tokens = max(0.0, self._tokens - 1.0)

    # ---- critical section: proxied request ---------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        data: Optional[Mapping[str, Any] | bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
        allow_redirects: bool = True,
        timeout: Optional[tuple[float, float] | float] = None,
        proxies: Optional[Mapping[str, str]] = None,
    ) -> requests.Response:
        with self._lock:
            self._throttle_token()
            return self._session.request(
                method=method, url=url,
                params=params, data=data, headers=headers,
                allow_redirects=allow_redirects, timeout=timeout, proxies=proxies
            )

    # ---- allow Requester to mount adapters / set headers --------------------
    def mount(self, prefix: str, adapter: requests.adapters.HTTPAdapter) -> None:
        self._session.mount(prefix, adapter)

    @property
    def headers(self):
        return self._session.headers

    @property
    def cookies(self):
        return self._session.cookies

    # Fallback for anything else
    def __getattr__(self, name: str):
        return getattr(self._session, name)
