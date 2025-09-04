"""
Holds the base class for all AO3 objects.
"""
import time
from typing import Optional, Union, Any, Callable

import requests
import warnings

import bs4
from bs4 import BeautifulSoup



class BasicSessionAPI:
    """
    Very basic stub to mock the only important bit of Ao3Session for this purpose.
    """
    @property
    def session(self) -> Optional[requests.session]:
        """
        Should mock the interface we need,

        :return:
        """
        raise NotImplementedError("Actually need a session.")


class BaseObjectAPI:
    """
    Contains the basic, internet connection methods which all classes are going to end up using.
    """

    _session: Optional[BasicSessionAPI]
    _main_page_rep: Optional[requests.Response]

    def __int__(self):
        """
        Just a stub.

        :return:
        """
        self._session = None
        self._main_page_rep = None

    def request(
        self,
        url: str,
        proxies: Optional[dict[str, str]] = None,
        set_main_url_req: bool = False,
        force_session: Optional[requests.Session] = None,

        retry_test: Optional[Callable[[BeautifulSoup], Optional[bs4._typing._AtMostOneElement]]] = None,
        retry_count: int = 5,
        retry_interval: float = 30.0

    ) -> BeautifulSoup:
        """Helper method - equest a web page and return a BeautifulSoup object.

        Args:
            url (str): Url to request
            proxies: Provide proxy options to the underlying call
            set_main_url_req: If True, will set the soup for the main page to this
            force_session: If True, then use this session to access the internet.

            retry_test: If provided, then a test function to see if the soup contains needed elements
            retry_count: How many retries to attempt if the soup does not have needed elements
            retry_interval: How many seconds to wait before retry

        Returns:
            bs4.BeautifulSoup: BeautifulSoup object representing the requested page's html
        """

        req = self.get(url, proxies=proxies, force_session=force_session)

        if len(req.content) > 650000:
            warnings.warn(
                "This work is very big and might take a very long time to load"
            )

        soup = BeautifulSoup(req.content, "lxml")

        # We can retry - so do so
        # - We have a retry test and it's failing
        if retry_test is not None and retry_test(soup) is None:

            assert isinstance(retry_count, int) and retry_count >= 1, f"Malformed retry count {retry_count = }"

            current_count = 0
            while current_count < retry_count:

                current_count += 1

                req = self.get(url, proxies=proxies, force_session=force_session)

                soup = BeautifulSoup(req.content, "lxml")
                if retry_test(soup) is not None:
                    break

                time.sleep(retry_interval)

        if set_main_url_req:
            self._main_page_rep = req

        soup = BeautifulSoup(req.content, "lxml")
        return soup

    def get(
        self,
        url: str,
        proxies: Optional[dict[str, str]] = None,
        allow_redirects: bool = True,
        timeout: Optional[Union[float, tuple[float, float]]] = None,
        force_session: Optional[requests.Session] = None,
    ) -> requests.Response:
        """
        Request a web page and return a Response object.

        """

        from ao3.requester import requester

        # We have not been provided a session to force use
        if force_session is None:

            if self._session is None:

                req = requester.request(
                    method="get",
                    url=url,
                    allow_redirects=allow_redirects,
                    timeout=timeout,
                    proxies=proxies,
                )
            else:

                # If we have an inbuilt session, then use that
                req = requester.request(
                    method="get",
                    url=url,
                    allow_redirects=allow_redirects,
                    force_session=self._session.session,
                    timeout=timeout,
                    proxies=proxies,
                )

        # We have been provided a force session - use it
        else:

            req = requester.request(
                method="get",
                url=url,
                allow_redirects=allow_redirects,
                force_session=force_session,
                timeout=timeout,
                proxies=proxies,
            )

        if req.status_code == 429:
            raise errors.HTTPException(
                "We are being rate-limited. Try again in a while or reduce the number of requests"
            )

        return req

    def post(
        self,
        url: str,
        params: Optional[
            Union[
                dict[str, Union[str, int, float, bool]],
                list[tuple[str, Union[str, int, float, bool]]],
                bytes,
            ]
        ] = None,
        allow_redirects: bool = False,
        headers: Optional[dict[str, str]] = None,
        data: Optional[dict[str, str]] = None,
        force_session: Optional[requests.Session] = None,
    ):
        """Make a post request with the current session

        Returns:
            requests.Request
        """
        from ao3.requester import requester

        if force_session is None:

            if self._session is None:

                req = requester.post(
                    url=url,
                    params=params,
                    allow_redirects=allow_redirects,
                    headers=headers,
                    data=data,
                )

            else:

                req = requester.post(
                    url=url,
                    params=params,
                    allow_redirects=allow_redirects,
                    force_session=self._session.session,
                    headers=headers,
                    data=data,
                )

        else:

            req = requester.post(
                url=url,
                params=params,
                allow_redirects=allow_redirects,
                force_session=force_session,
                headers=headers,
                data=data,
            )

        if req.status_code == 429:
            raise errors.RateLimitedException(
                "We are being rate-limited. Try again in a while or reduce the number of requests"
            )
        return req

    @staticmethod
    def str_format(string: str):
        """Formats a given string

        Args:
            string (str): String to format

        Returns:
            str: Formatted string
        """

        return string.replace(",", "")

    def __getstate__(self) -> dict[str, Any]:
        """
        Return the current state of the class.

        :return:
        """
        d = {}
        for attr in self.__dict__:
            if isinstance(self.__dict__[attr], BeautifulSoup):
                d[attr] = (self.__dict__[attr].encode(), True)
            else:
                d[attr] = (self.__dict__[attr], False)
        return d

    def __setstate__(self, d: dict[str, Any]):
        """
        Write the saved state back out to itself.

        :param d:
        :return:
        """
        for attr in d:
            value, issoup = d[attr]
            if issoup:
                self.__dict__[attr] = BeautifulSoup(value, "lxml")
            else:
                self.__dict__[attr] = value
