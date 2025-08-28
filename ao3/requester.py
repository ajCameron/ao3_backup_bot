# ao3/requester.py
from __future__ import annotations

import time
from typing import Optional, Mapping, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ao3.errors import NetworkException, RateLimitedException


class Requester:
    """
    Lightweight request helper that can use an external authenticated session.
    Adds throttling, typed exceptions, and lazily mounts HTTPAdapter+Retry
    onto whichever session is actually used for a call.
    """

    def __init__(
        self,
        requests_per_window: int = 60,
        window_seconds: float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
        allowed_methods: tuple[str, ...] = ("GET", "HEAD", "OPTIONS", "POST"),
        pool_connections: int = 10,
        pool_maxsize: int = 10,
        default_timeout: tuple[float, float] | float = (5.0, 30.0),
        user_agent: str = "ao3.py (+https://example)",
        session: Optional[requests.Session] = None,
    ):
        # throttle state
        self._capacity = max(1, int(requests_per_window))
        self._window = float(window_seconds)
        self._tokens = self._capacity
        self._last = time.monotonic()

        # retry/adapter params
        self._retry = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=allowed_methods,
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        self._pool_connections = pool_connections
        self._pool_maxsize = pool_maxsize

        # defaults
        self._default_timeout = default_timeout
        self._default_headers: dict[str, str] = {
            "User-Agent": user_agent,
            "Accept": "*/*",
        }

        self.session: Optional[requests.Session] = session

    # ---- Session helpers ----
    def attach_session(self, session: requests.Session) -> None:
        self._ensure_adapters(session)
        self._ensure_default_headers(session)
        self.session = session

    def detach_session(self) -> None:
        self.session = None

    def configure_session(self, session: requests.Session) -> None:
        """Explicitly mount adapters and headers once on a session."""
        self._ensure_adapters(session)
        self._ensure_default_headers(session)

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        data: Optional[Mapping[str, Any] | bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
        allow_redirects: bool = True,
        timeout: Optional[tuple[float, float] | float] = None,
        proxies: Optional[Mapping[str, str]] = None,
        force_session: Optional[requests.Session] = None,
    ) -> requests.Response:
        """
        Finally request the actual page.

        :param method:
        :param url:
        :param params:
        :param data:
        :param headers:
        :param allow_redirects:
        :param timeout:
        :param proxies:
        :param force_session:
        :return:
        """
        self._throttle()

        sess = force_session or self.session or requests.Session()

        # If we have an external setup session, we just want to use it
        if force_session is None:
            self._ensure_adapters(sess)
            self._ensure_default_headers(sess)

        merged_headers = dict(self._default_headers)
        if headers:
            merged_headers.update(headers)

        try:
            resp = sess.request(
                method=method,
                url=url,
                params=params,
                data=data,
                headers=merged_headers,
                allow_redirects=allow_redirects,
                timeout=self._default_timeout if timeout is None else timeout,
                proxies=proxies,
            )
        except requests.RequestException as e:
            raise NetworkException(str(e), url=url, method=method) from e

        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            raise RateLimitedException(retry_after=retry_after)

        return resp

    def get(
        self,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        allow_redirects: bool = True,
        timeout: Optional[tuple[float, float] | float] = None,
        proxies: Optional[Mapping[str, str]] = None,
        force_session: Optional[requests.Session] = None,
    ) -> requests.Response:
        """
        We're executing a get request.

        :param url:
        :param params:
        :param headers:
        :param allow_redirects:
        :param timeout:
        :param proxies:
        :param force_session:
        :return:
        """
        return self.request(
            "GET",
            url,
            params=params,
            headers=headers,
            allow_redirects=allow_redirects,
            timeout=timeout,
            proxies=proxies,
            force_session=force_session,
        )

    def post(
        self,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        data: Optional[Mapping[str, Any] | bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
        allow_redirects: bool = True,
        timeout: Optional[tuple[float, float] | float] = None,
        proxies: Optional[Mapping[str, str]] = None,
        force_session: Optional[requests.Session] = None,
    ) -> requests.Response:
        return self.request(
            "POST",
            url,
            params=params,
            data=data,
            headers=headers,
            allow_redirects=allow_redirects,
            timeout=timeout,
            proxies=proxies,
            force_session=force_session,
        )

    # ---- internals ----
    def _throttle(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._last = now

        self._tokens = min(self._capacity, self._tokens + elapsed * (self._capacity / self._window))
        if self._tokens < 1:
            sleep_for = (1 - self._tokens) * (self._window / self._capacity)
            time.sleep(sleep_for)
            self._tokens = 0
        self._tokens = max(0, self._tokens - 1)

    def _ensure_adapters(self, session: requests.Session) -> None:
        """
        Ensure our custom adapter is mounted onto the session.

        :param session:
        :return:
        """
        if getattr(session, "_ao3_adapters_installed", False):
            return
        adapter = HTTPAdapter(
            max_retries=self._retry,
            pool_connections=self._pool_connections,
            pool_maxsize=self._pool_maxsize,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        setattr(session, "_ao3_adapters_installed", True)

    def _ensure_default_headers(self, session: requests.Session) -> None:
        if getattr(session, "_ao3_headers_installed", False):
            return
        for k, v in self._default_headers.items():
            session.headers.setdefault(k, v)
        setattr(session, "_ao3_headers_installed", True)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# Module-level singleton, same as before
requester = Requester()

__all__ = ["requester", "Requester"]
