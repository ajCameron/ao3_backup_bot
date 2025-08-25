"""
Wwraps requests in a convenience class for easier use.

(Mostly makes it harder to hit the rate limits)>
"""

import threading
import time

import requests

from typing import Optional, Union


class Requester:
    """Requester object"""

    _rqtw: int
    _timew: int
    _lock: threading.Lock
    total: int

    def __init__(self, rqtw: int = -1, timew: int = 60) -> None:
        """Limits the request rate to prevent HTTP 429 (rate limiting) responses.
        12 request per minute seems to be the limit.

        Args:
            rqtw (int, optional): Maximum requests per time window (-1 -> no limit). Defaults to -1.
            timew (int, optional): Time window (seconds). Defaults to 60.
        """

        self._requests = []
        self._rqtw = rqtw
        self._timew = timew
        self._lock = threading.Lock()
        self.total = 0

    def setRQTW(self, value: int) -> None:
        """
        Sets the maximum number of requests per time window.

        :param value:
        :return:
        """
        self._rqtw = value

    def setTimeW(self, value: int) -> None:
        """
        Sets the time window.

        :param value:
        :return:
        """
        self._timew = value

    def request(
        self,
        method: str,
        url: str,
        params: Optional[
            Union[
                dict[str, Union[str, int, float, bool]],
                list[tuple[str, Union[str, int, float, bool]]],
                bytes,
            ]
        ] = None,
        allow_redirects: bool = True,
        headers: Optional[dict[str, str]] = None,
        data: Optional[dict[str, str]] = None,
        proxies: Optional[dict[str, str]] = None,
        timeout: Optional[Union[float, tuple[float, float]]] = None,
        session: Optional["Session"] = None,
    ) -> requests.Response:
        """Requests a web page once enough time has passed since the last request

        Args:
            session(requests.Session, optional): Session object to request with

        Returns:
            requests.Response: Response object
        """

        # We've made a bunch of requests, time to rate limit?
        if self._rqtw != -1:
            with self._lock:
                if len(self._requests) >= self._rqtw:
                    t = time.time()
                    # Reduce list to only requests made within the current time window
                    while len(self._requests):
                        if t - self._requests[0] >= self._timew:
                            self._requests.pop(0)  # Older than window, forget about it
                        else:
                            break  # Inside window, the rest of them must be too
                    # Have we used up all available requests within our window?
                    if len(self._requests) >= self._rqtw:  # Yes
                        # Wait until the oldest request exits the window, giving us a slot for the new one
                        time.sleep(self._requests[0] + self._timew - t)
                        # Now outside window, drop it
                        self._requests.pop(0)

                if self._rqtw != -1:
                    self._requests.append(time.time())
                self.total += 1

        if session is not None:
            req = session.request(
                method,
                url,
                proxies=proxies,
                params=params,
                allow_redirects=allow_redirects,
                data=data,
                headers=headers,
                timeout=timeout,
            )
        else:
            req = requests.request(
                method,
                url,
                proxies=proxies,
                params=params,
                allow_redirects=allow_redirects,
                data=data,
                headers=headers,
                timeout=timeout,
            )

        return req


requester = Requester()

__all__ = ["Requester", "requester"]
